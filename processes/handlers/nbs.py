# Copyright (C) 2025 Deltares
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
import os
from pathlib import Path

import fiona
import geopandas as gpd
import numpy as np

from processes.config import get_config
from processes.utils import load_reclass_table
from processes.utils.geoserver import publish_and_respond
from processes.utils.raster import aggregate_raster_histogram_to_hexagons
from processes.utils.session import load_session

logger = logging.getLogger(__name__)

_CLC_NODATA = 48


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


def main_handler(session_id: str, archetype: str) -> list:
    """Add per-hexagon CLC zonal histogram columns and republish the UoM layer."""
    cfg = get_config()
    session_dir = load_session(session_id)
    archetype_lower = archetype.lower()

    clc_path = _require_clc_tif(session_dir)
    hexgrid_path = _require_uom_gpkg(session_dir, session_id, archetype_lower)
    classes = _clc_classes_from_lut(cfg)

    logger.info(
        'lare-nbs: session=%s archetype=%s classes=%d hexagons=%s',
        session_id,
        archetype_lower,
        len(classes),
        hexgrid_path.name,
    )

    hexagons = gpd.read_file(hexgrid_path)
    hexagons = aggregate_raster_histogram_to_hexagons(
        clc_path,
        hexagons,
        classes=classes,
        column_prefix='clc_',
    )
    # Preserve existing layer name when overwriting the same GeoPackage.
    layer_names = list(fiona.listlayers(str(hexgrid_path)))
    layer_name = layer_names[0] if layer_names else hexgrid_path.stem
    hexagons.to_file(hexgrid_path, layer=layer_name, driver='GPKG', mode='w')
    logger.info('Histogram columns written to %s', hexgrid_path)

    return publish_and_respond(
        hexgrid_path,
        'NBS per UOM',
        {'nbs': 'NBS per UOM'},
    )
