# Copyright (C) 2025 Deltares
# SPDX-License-Identifier: GPL-3.0-or-later

# native
import os
import logging

# imports
import geopandas as gpd
import numpy as np
import fiona

# local
from processes.config import get_config, KcsAggregation, KcsEntry
from processes.utils.session import load_session
from processes.utils import load_reclass_table
from processes.utils.wfs import clip_from_wfs_cql
from processes.utils.vector import ensure_metric
from processes.utils.geoserver import filter_vector_by_vector, create_viewer_output, republish_layer
from processes.utils.raster import (
    lare_raster,
    aggregate_hazard,
    aggregate_raster_to_hexagons,
)
logger = logging.getLogger(__name__)


def _require_uom_gpkg(session_dir, session_id: str, archetype: str) -> str:
    """Build and validate the expected UoM GeoPackage path."""
    uom_gpkg = str(session_dir / f'hexagons_{archetype}_{session_id}.gpkg')
    if not os.path.isfile(uom_gpkg):
        raise FileNotFoundError(f'Hexagon file not found: {uom_gpkg}')
    return uom_gpkg


def _resolve_kcs_layer(cfg, kcs: str) -> tuple[str, KcsEntry]:
    """Resolve KCS key to (layer_name, KcsEntry) from config."""
    for layer_name, entry in cfg.kcs.items():
        if kcs in layer_name:
            return layer_name, entry
    raise ValueError(f'KCS {kcs!r} not found in config layers.kcs')


def _require_hazard_raster(uom: gpd.GeoDataFrame, hazard_layer: str, session_id: str) -> str:
    """Clip and validate hazard raster output path."""
    hazard_tif = lare_raster(uom, 4326, hazard_layer, session_id)
    if not hazard_tif or not os.path.isfile(hazard_tif):
        raise RuntimeError(f'Hazard raster not produced for layer {hazard_layer!r}')
    return hazard_tif


def _aggregate_kcs_uom(kcs_gdf, uom_gdf, entry: KcsEntry, session_id=None):
    """Aggregate vector KCS features into UoM hexagons.

    Dispatches to the correct aggregation strategy based on ``entry.aggregation``:

    * ``length``  – sum line geometry length inside each hexagon (metres, EPSG:3035)
    * ``count``   – count distinct intersecting features per hexagon
    * ``area``    – sum clipped polygon area inside each hexagon (m², EPSG:3035)

    Args:
        kcs_gdf: KCS features as a GeoDataFrame (vector).
        uom_gdf: UoM features as a GeoDataFrame to aggregate into.
        entry: :class:`~processes.config.KcsEntry` carrying type and aggregation kind.
        session_id: Optional session identifier for logging/context.

    Returns:
        gpd.GeoDataFrame: Updated UoM GeoDataFrame with an aggregated output column.
    """
    if kcs_gdf is None:
        raise RuntimeError("KCS input is None, cannot aggregate to UoM")

    if not isinstance(kcs_gdf, gpd.GeoDataFrame):
        raise RuntimeError(f"KCS input must be a GeoDataFrame, got {type(kcs_gdf)}")

    if not isinstance(uom_gdf, gpd.GeoDataFrame):
        raise RuntimeError(f"UoM input must be a GeoDataFrame, got {type(uom_gdf)}")

    if kcs_gdf.empty:
        logger.warning("!-- aggregate_kcs_uom: kcs_gdf is empty, writing zero values to UoM")

    uom = uom_gdf.copy()

    if uom.empty:
        raise RuntimeError("UoM dataset is empty")

    # Ensure a stable key exists for merging.
    if 'id' not in uom.columns:
        logger.warning("!-- aggregate_kcs_uom: 'id' column not found in UoM, creating from index")
        uom = uom.reset_index(drop=False).rename(columns={'index': 'id'})

    # Reproject KCS data to UoM CRS when needed.
    if kcs_gdf.crs != uom.crs:
        kcs_gdf = kcs_gdf.to_crs(uom.crs)

    # Work in projected coordinates for meaningful length/area calculations.
    uom_calc = ensure_metric(uom, 3035)
    kcs_gdf_calc = ensure_metric(kcs_gdf, 3035)

    aggregation_name = entry.aggregation.value
    output_column = entry.output_column or f'kcs_aggregation_{aggregation_name}'

    # Spatial join: keep UoM as left frame so we can aggregate by hexagon id.
    sjoin_result = gpd.sjoin(uom_calc[['id', 'geometry']], kcs_gdf_calc[['geometry']], how='inner', predicate='intersects')

    if sjoin_result.empty:
        aggregated = uom[['id']].copy()
        aggregated[output_column] = 0.0
    elif entry.aggregation == KcsAggregation.count:
        aggregated = (
            sjoin_result.groupby('id', as_index=False)['index_right']
            .nunique()
            .rename(columns={'index_right': output_column})
        )
    elif entry.aggregation == KcsAggregation.length:
        kcs_lengths = kcs_gdf_calc.geometry.length
        sjoin_result[output_column] = sjoin_result['index_right'].map(kcs_lengths)
        sjoin_result[output_column] = sjoin_result[output_column].fillna(0)
        aggregated = sjoin_result.groupby('id', as_index=False)[output_column].sum()
    else:
        raise ValueError(f"Unknown aggregation kind: {entry.aggregation!r}")
    
    
    if output_column in uom.columns:
        uom = uom.drop(columns=[output_column])

    uom = uom.merge(aggregated, on='id', how='left')
    uom[output_column] = uom[output_column].fillna(0)

    return uom


def _aggregate_kcs_raster_uom(
    outkcs_tif: str,
    uom_gpkg: str,
    csv_path: str,
    kcs: str,
    entry: KcsEntry,
) -> str:
    """Aggregate raster KCS to UoM using the configured raster statistic."""
    if not outkcs_tif or not os.path.isfile(outkcs_tif):
        raise FileNotFoundError(f'Raster KCS file not found: {outkcs_tif}')

    layer_names = fiona.listlayers(uom_gpkg)
    if not layer_names:
        raise RuntimeError(f"No layers found in {uom_gpkg}")
    uom_layer = layer_names[0]

    uom = gpd.read_file(uom_gpkg, layer=uom_layer, engine='pyogrio')
    if uom.empty:
        raise RuntimeError("UoM dataset is empty")

    # Use same LUT loader pattern as in uom.py.
    clc_to_lac = load_reclass_table(csv_path, lusecol='clc', reclasscol='lac')
    if clc_to_lac is None:
        raise ValueError(f'Failed to load reclassification table from {csv_path}')

    # For agriculture KCS, keep rural/agricultural archetype classes (lac == 3).
    if kcs.lower() == 'agriculture':
        classes = [int(clc) for clc, lac in clc_to_lac.items() if np.isfinite(lac) and int(lac) == 3]
        logger.info('uomkcs agriculture CLC classes selected: %s', classes)
    else:
        classes = [int(clc) for clc, lac in clc_to_lac.items() if np.isfinite(lac)]

    if not classes:
        raise ValueError(f'No valid CLC classes found for KCS {kcs!r}')

    raster_stat = entry.aggregation.value
    output_column = entry.output_column or f'kcs_aggregation_{raster_stat}'
    logger.info('uomkcs: raster aggregation for %r uses stat=%s', kcs, raster_stat)
    raster_stat_alias = 'majority' if raster_stat == KcsAggregation.mode.value else raster_stat
    uom = aggregate_raster_to_hexagons(
        outkcs_tif,
        uom,
        stat=raster_stat_alias,
        classes=classes,
    )
    if output_column in uom.columns:
        uom = uom.drop(columns=[output_column])
    uom.rename(columns={'aggregated_value': output_column}, inplace=True)
    uom[output_column] = uom[output_column].fillna(0)

    uom.to_file(uom_gpkg, layer=uom_layer, driver='GPKG', mode='w')
    return uom_gpkg



def main_handler(session_id, kcs, hazard, archetype):
    cfg = get_config()
    geoserver_url = cfg.ows_base
    wms_url = cfg.geoserver.url

    session_dir = load_session(session_id)
    uom_gpkg = _require_uom_gpkg(session_dir, session_id, archetype)

    #TODO: add the correct hazard layer to the config. E.g drought.
    hazard_layer = cfg.hazard_layers[hazard]
    logger.info('uomkcs: hazard %r -> layer %s', hazard, hazard_layer)

    uom = gpd.read_file(uom_gpkg)
    #In this step we are clipping the hazard layer to the UoM.
    hazard_tif = _require_hazard_raster(uom, hazard_layer, session_id)
    #In this step we are reading from the config the KCS layer and its entry.
    kcs_layer, entry = _resolve_kcs_layer(cfg, kcs)

    if entry.type.value == 'raster':
        out_kcs = lare_raster(uom, uom.crs, kcs_layer, session_id=session_id)
        logger.debug('uomkcs: KCS %r clipped as raster: %s', kcs, out_kcs)
        csv_path = os.path.normpath(
            os.path.join(os.path.dirname(__file__), '..', '..', cfg.hazard_clc_scores['archetype'])
        )
        _aggregate_kcs_raster_uom(out_kcs, uom_gpkg, csv_path, kcs, entry)

    elif entry.type.value == 'vector':
        layer_names = fiona.listlayers(uom_gpkg)
        if not layer_names:
            raise RuntimeError(f"No layers found in {uom_gpkg}")
        uom_layer = layer_names[0]

        filter_gdf = gpd.GeoDataFrame(geometry=[uom.geometry.unary_union], crs=uom.crs)
        kcs_gdf = filter_vector_by_vector(geoserver_url, filter_gdf, filter_gdf.crs, kcs_layer, 4326)
        if kcs_gdf is not None and not kcs_gdf.empty:
            logger.info('uomkcs: KCS %r clipped, %d features (aggregation: %s)', kcs, len(kcs_gdf), entry.aggregation)
            uom = _aggregate_kcs_uom(kcs_gdf, uom, entry, session_id=session_id)
            uom.to_file(uom_gpkg, layer=uom_layer, driver='GPKG', mode='w')
        else:
            logger.warning('uomkcs: no features returned for KCS %r', kcs)
    else:
        raise ValueError(f'Unsupported KCS type {entry.type!r} for {kcs!r}')

    aggregate_hazard(session_id, hazard_tif, archetype)

    layer_name = f'hexagons_{archetype}_{session_id}_{kcs}'
    republish_layer(f'hexagons_{archetype}_{session_id}', workspace='tmp', style_name=entry.style, layer_name=layer_name)
    return create_viewer_output([layer_name], 'Aggregated KCS', {'uom': 'Aggregated KCS'}, wms_url)