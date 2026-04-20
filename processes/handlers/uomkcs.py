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
from processes.handlers.session import load_session
from processes.utils.wfs import clipfromwfs_cql
from processes.utils.vector import ensure_metric
from processes.utils.geoserver import filter_vector_by_vector, createvieweroutput, republish_layer
from processes.utils.raster import lare_raster, aggregate_hazard

logger = logging.getLogger(__name__)


def _require_uom_gpkg(sessiondir, sessionid: str, archetype: str) -> str:
    """Build and validate the expected UoM GeoPackage path."""
    uom_gpkg = str(sessiondir / f'hexagons_{archetype}_{sessionid}.gpkg')
    if not os.path.isfile(uom_gpkg):
        raise FileNotFoundError(f'Hexagon file not found: {uom_gpkg}')
    return uom_gpkg


def _resolve_kcs_layer(cfg, kcs: str) -> tuple[str, KcsEntry]:
    """Resolve KCS key to (layer_name, KcsEntry) from config."""
    for layer_name, entry in cfg.kcs.items():
        if kcs in layer_name:
            return layer_name, entry
    raise ValueError(f'KCS {kcs!r} not found in config layers.kcs')


def _require_hazard_raster(uom: gpd.GeoDataFrame, hazardlayer: str, sessionid: str) -> str:
    """Clip and validate hazard raster output path."""
    hazardtif = lare_raster(uom, 4326, hazardlayer, sessionid)
    if not hazardtif or not os.path.isfile(hazardtif):
        raise RuntimeError(f'Hazard raster not produced for layer {hazardlayer!r}')
    return hazardtif


def test():
    # Load the GeoPackage files
    hexagons_gpkg = 'path/to/hexagons.gpkg'
    lines_gpkg = 'path/to/lines.gpkg'

    hexagons = gpd.read_file(hexagons_gpkg, layer='hexagons')
    lines = gpd.read_file(lines_gpkg, layer='lines')

    # Perform the spatial join
    sjoin_result = gpd.sjoin(hexagons, lines, how="inner", op='intersects')

    # Calculate the total length of lines within each hexagon
    sjoin_result['line_length'] = sjoin_result['geometry'].length
    hexagon_lengths = sjoin_result.groupby('index_right')['line_length'].sum().reset_index()

    # Rename the columns to match the original hexagon GeoDataFrame
    hexagon_lengths.rename(columns={'index_right': 'id', 'line_length': 'total_length'}, inplace=True)

    # Merge the total lengths back into the original hexagon GeoDataFrame
    hexagons = hexagons.merge(hexagon_lengths, on='id', how='left')

    # Save the updated hexagon GeoDataFrame back to a GeoPackage file
    output_gpkg = 'path/to/output_hexagons.gpkg'
    hexagons.to_file(output_gpkg, layer='hexagons', driver='GPKG')

    logger.debug("Updated hexagon GeoPackage file saved to: %s", output_gpkg)
def _aggregate_kcs_uom(kcs_gdf, uom_gdf, entry: KcsEntry, sessionid=None):
    """Aggregate vector KCS features into UoM hexagons.

    Dispatches to the correct aggregation strategy based on ``entry.aggregation``:

    * ``length``  – sum line geometry length inside each hexagon (metres, EPSG:3035)
    * ``count``   – count distinct intersecting features per hexagon
    * ``area``    – sum clipped polygon area inside each hexagon (m², EPSG:3035)

    Args:
        kcs_gdf: KCS features as a GeoDataFrame (vector).
        uom_gdf: UoM features as a GeoDataFrame to aggregate into.
        entry: :class:`~processes.config.KcsEntry` carrying type and aggregation kind.
        sessionid: Optional session identifier for logging/context.

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



def mainhandler(sessionid, kcs, hazard, archetype):
    cfg = get_config()
    geoserver_url = cfg.ows_base
    wmsurl = cfg.geoserver.url

    sessiondir = load_session(sessionid)
    uom_gpkg = _require_uom_gpkg(sessiondir, sessionid, archetype)

    #TODO: add the correct hazard layer to the config. E.g drought.
    hazardlayer = cfg.hazard_layers[hazard]
    logger.info('uomkcs: hazard %r -> layer %s', hazard, hazardlayer)

    uom = gpd.read_file(uom_gpkg)
    #In this step we are clipping the hazard layer to the UoM.
    hazardtif = _require_hazard_raster(uom, hazardlayer, sessionid)
    #In this step we are reading from the config the KCS layer and its entry.
    kcslayer, entry = _resolve_kcs_layer(cfg, kcs)

    if entry.type.value == 'raster':
        kcs_gdf = lare_raster(uom, uom.crs, kcs)
        logger.debug('uomkcs: KCS %r clipped as raster: %s', kcs, kcs_gdf)

    elif entry.type.value == 'vector':
        layer_names = fiona.listlayers(uom_gpkg)
        if not layer_names:
            raise RuntimeError(f"No layers found in {uom_gpkg}")
        uom_layer = layer_names[0]

        filter_gdf = gpd.GeoDataFrame(geometry=[uom.geometry.unary_union], crs=uom.crs)
        kcs_gdf = filter_vector_by_vector(geoserver_url, filter_gdf, filter_gdf.crs, kcslayer, 4326)
        if kcs_gdf is not None and not kcs_gdf.empty:
            logger.info('uomkcs: KCS %r clipped, %d features (aggregation: %s)', kcs, len(kcs_gdf), entry.aggregation)
            uom = _aggregate_kcs_uom(kcs_gdf, uom, entry, sessionid=sessionid)
            uom.to_file(uom_gpkg, layer=uom_layer, driver='GPKG', mode='w')
        else:
            logger.warning('uomkcs: no features returned for KCS %r', kcs)
    else:
        raise ValueError(f'Unsupported KCS type {entry.type!r} for {kcs!r}')

    aggregate_hazard(sessionid, hazardtif, archetype)

    layer_name = f'hexagons_{archetype}_{sessionid}_{kcs}'
    republish_layer(f'hexagons_{archetype}_{sessionid}', workspace='tmp', style_name=entry.style, layer_name=layer_name)
    return createvieweroutput([layer_name], 'Aggregated KCS', {'uom': 'Aggregated KCS'}, wmsurl)