# Copyright (C) 2025 Deltares
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
import os
from pathlib import Path

import fiona
import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio

from processes.config import get_config
from processes.utils import load_reclass_table
from processes.utils.geoserver import publish_and_respond
from processes.utils.raster import aggregate_raster_histogram_to_hexagons
from processes.utils.session import load_session

logger = logging.getLogger(__name__)

_CLC_NODATA = 48
_TOP_N = 5
_NBS_SEP = ';'


def _require_clc_tif(session_dir: Path) -> str:
    clc_path = session_dir / 'clc.tif'
    if not clc_path.is_file():
        raise FileNotFoundError(
            f'CLC raster not found: {clc_path}. '
            'Run lare-uom with archetype urban, rural, or coastal first.'
        )
    return str(clc_path)


def _require_uom_gpkg(session_dir: Path, session_id: str, archetype: str) -> Path:
    uom_gpkg = session_dir / f'hexagons_{archetype}_{session_id}.gpkg'
    if not uom_gpkg.is_file():
        raise FileNotFoundError(f'Hexagon file not found: {uom_gpkg}')
    return uom_gpkg


def _clc_classes_from_lut(cfg) -> list[int]:
    """Return remapped CLC codes from the archetype LUT, excluding NODATA."""
    csv_path = os.path.normpath(
        os.path.join(os.path.dirname(__file__), '..', '..', cfg.hazard_clc_scores['archetype'])
    )
    clc_to_lac = load_reclass_table(csv_path, lusecol='clc', reclasscol='lac')
    if clc_to_lac is None:
        raise ValueError(f'Failed to load CLC reclass table from {csv_path}')

    classes = sorted(
        {
            int(clc)
            for clc in clc_to_lac.keys()
            if np.isfinite(clc) and int(clc) != _CLC_NODATA
        }
    )
    if not classes:
        raise ValueError(f'No CLC classes found in {csv_path}')
    return classes


def _hazard_csv_labels(hazard: str) -> list[str]:
    """Resolve a process hazard key to CSV labels via ``hazards.nbs_labels``."""
    cfg = get_config()
    labels_map = cfg.hazard_nbs_labels or {}
    key = hazard.strip()
    # Prefer exact key, then case-insensitive match.
    if key in labels_map:
        labels = labels_map[key]
    else:
        lower = key.lower()
        labels = next((v for k, v in labels_map.items() if k.lower() == lower), None)

    if not labels:
        available = sorted(labels_map.keys())
        raise ValueError(
            f'Hazard {hazard!r} has no NBS label mapping in app.yml '
            f'(hazards.nbs_labels). Available keys: {available}'
        )
    return [str(label).strip() for label in labels if str(label).strip()]


def _repo_data_path(*parts: str) -> Path:
    return Path(__file__).resolve().parents[2].joinpath(*parts)


def _build_nbs_lookup(archetype: str, hazard: str) -> dict[int, list[str]]:
    """Map remapped CLC code → sorted unique NBS codes for archetype + hazard.

    Uses the harmonized NBS table from ``hazards.nbs_table`` (default
    ``data/clc_nbs_hazard_updated.csv``), filtered by ``hazard`` labels from
    ``hazards.nbs_labels`` and ``landscape_case`` matching the process archetype.
    """
    cfg = get_config()
    nbs_rel = cfg.hazard_nbs_table or 'data/clc_nbs_hazard_updated.csv'
    nbs_path = _repo_data_path(*Path(nbs_rel).parts)
    if not nbs_path.is_file():
        raise FileNotFoundError(f'NBS mapping not found: {nbs_path}')

    nbs = pd.read_csv(nbs_path)
    required = {'clc', 'hazard', 'nbs_code', 'landscape_case'}
    missing = required - set(nbs.columns)
    if missing:
        raise ValueError(f'NBS table {nbs_path} missing columns: {sorted(missing)}')

    nbs['hazard'] = nbs['hazard'].astype(str).str.strip()
    nbs['nbs_code'] = nbs['nbs_code'].astype(str).str.strip()
    nbs['landscape_case'] = nbs['landscape_case'].astype(str).str.strip()
    nbs.loc[nbs['landscape_case'].str.lower().isin({'nan', ''}), 'landscape_case'] = pd.NA

    case = archetype.strip().lower()
    nbs_case = nbs[nbs['landscape_case'].str.lower() == case].copy()
    if nbs_case.empty:
        raise ValueError(
            f'No NBS rows for landscape_case={archetype!r} in {nbs_path}'
        )

    hazard_labels = {h.lower() for h in _hazard_csv_labels(hazard)}
    nbs_haz = nbs_case[nbs_case['hazard'].str.lower().isin(hazard_labels)].copy()
    if nbs_haz.empty:
        logger.warning(
            'lare-nbs: no NBS rows for hazard=%r (labels=%s) case=%s',
            hazard,
            sorted(hazard_labels),
            case,
        )
        return {}

    lookup: dict[int, list[str]] = {}
    for clc_code, group in nbs_haz.groupby('clc'):
        codes = sorted({str(c) for c in group['nbs_code'].dropna() if str(c) and str(c) != 'nan'})
        if codes:
            lookup[int(clc_code)] = codes
    logger.info(
        'lare-nbs: NBS lookup built for archetype=%s hazard=%s (%d CLC codes with NBS) from %s',
        case,
        hazard,
        len(lookup),
        nbs_path.name,
    )
    return lookup


def _annotate_nbs_columns(
    hexagons: gpd.GeoDataFrame,
    archetype: str,
    hazard: str,
    pixel_area_m2: float,
    top_n: int = _TOP_N,
    column_prefix: str = 'clc_',
) -> gpd.GeoDataFrame:
    """Add display nbs_list_* for top ranks plus full-depth NBS majority columns.

    * ``nbs_list_1`` … ``nbs_list_{top_n}`` – NBS codes for displayed ranks only
      (empty string when that ranked CLC has no NBS).
    * ``clc_nbs_majority`` / ``nbs_list_majority`` / ``clc_nbs_majority_area`` –
      first CLC with pixel count > 0 (by descending count across **all**
      histogram classes) that has NBS for this hazard and archetype. Area is
      majority-class pixel count × CLC pixel ground area (m²). Search is not
      limited to ``top_n``.
    """
    lookup = _build_nbs_lookup(archetype, hazard)
    n = len(hexagons)

    drop_cols = ['clc_nbs_majority', 'nbs_list_majority', 'clc_nbs_majority_area', 'clc_majority_area']
    drop_cols.extend(
        c for c in hexagons.columns
        if c.startswith('nbs_flag_') or c.startswith('nbs_list_')
    )
    drop_cols = list(dict.fromkeys(drop_cols))
    existing = [c for c in drop_cols if c in hexagons.columns]
    if existing:
        hexagons = hexagons.drop(columns=existing)

    # Histogram count columns: clc_1, clc_12, … (exclude rank/majority names).
    count_cols: list[tuple[int, str]] = []
    prefix_len = len(column_prefix)
    for col in hexagons.columns:
        if not col.startswith(column_prefix):
            continue
        suffix = col[prefix_len:]
        if suffix.isdigit():
            count_cols.append((int(suffix), col))
    count_cols.sort(key=lambda t: t[0])

    lists = {i: np.array([''] * n, dtype=object) for i in range(1, top_n + 1)}
    nbs_majority = np.full(n, np.nan)
    nbs_list_majority = np.array([''] * n, dtype=object)
    nbs_majority_area = np.full(n, np.nan)

    for row_i in range(n):
        row = hexagons.iloc[row_i]

        # Display lists for the published top-N ranks only.
        for rank in range(1, top_n + 1):
            rank_col = f'clc_rank_{rank}'
            if rank_col not in hexagons.columns:
                continue
            raw = row[rank_col]
            if raw is None or (isinstance(raw, float) and np.isnan(raw)):
                continue
            clc_code = int(raw)
            nbs_codes = lookup.get(clc_code, [])
            lists[rank][row_i] = _NBS_SEP.join(nbs_codes) if nbs_codes else ''

        # Full-depth majority: all CLC classes with count > 0, highest count first.
        present: list[tuple[int, int]] = []  # (count, clc_code)
        for clc_code, col in count_cols:
            try:
                count_val = int(row[col]) if row[col] is not None else 0
            except (TypeError, ValueError):
                count_val = 0
            if count_val > 0:
                present.append((count_val, clc_code))
        present.sort(key=lambda t: (-t[0], t[1]))

        for count_val, clc_code in present:
            nbs_codes = lookup.get(clc_code, [])
            if nbs_codes:
                nbs_majority[row_i] = float(clc_code)
                nbs_list_majority[row_i] = _NBS_SEP.join(nbs_codes)
                nbs_majority_area[row_i] = float(count_val) * float(pixel_area_m2)
                break

    for rank in range(1, top_n + 1):
        hexagons[f'nbs_list_{rank}'] = lists[rank]
    hexagons['clc_nbs_majority'] = nbs_majority
    hexagons['nbs_list_majority'] = nbs_list_majority
    hexagons['clc_nbs_majority_area'] = nbs_majority_area
    return hexagons


def main_handler(session_id: str, archetype: str, hazard: str) -> list:
    """Add CLC histogram, ranks, and NBS columns; republish the UoM layer."""
    cfg = get_config()
    session_dir = load_session(session_id)
    archetype_lower = archetype.lower()

    clc_path = _require_clc_tif(session_dir)
    hexgrid_path = _require_uom_gpkg(session_dir, session_id, archetype_lower)
    classes = _clc_classes_from_lut(cfg)

    logger.info(
        'lare-nbs: session=%s archetype=%s hazard=%s classes=%d hexagons=%s',
        session_id,
        archetype_lower,
        hazard,
        len(classes),
        hexgrid_path.name,
    )

    hexagons = gpd.read_file(hexgrid_path)
    hexagons = aggregate_raster_histogram_to_hexagons(
        clc_path,
        hexagons,
        classes=classes,
        column_prefix='clc_',
        top_n=_TOP_N,
    )
    with rasterio.open(clc_path) as src:
        pixel_area_m2 = abs(float(src.transform.a)) * abs(float(src.transform.e))
    logger.info('lare-nbs: CLC pixel_area_m2=%.3f', pixel_area_m2)
    hexagons = _annotate_nbs_columns(
        hexagons,
        archetype_lower,
        hazard,
        pixel_area_m2=pixel_area_m2,
        top_n=_TOP_N,
    )

    # Preserve existing layer name when overwriting the same GeoPackage.
    layer_names = list(fiona.listlayers(str(hexgrid_path)))
    layer_name = layer_names[0] if layer_names else hexgrid_path.stem
    hexagons.to_file(hexgrid_path, layer=layer_name, driver='GPKG', mode='w')
    logger.info('NBS / histogram columns written to %s', hexgrid_path)

    return publish_and_respond(
        hexgrid_path,
        'NBS per UOM',
        {'nbs': 'NBS per UOM'},
    )
