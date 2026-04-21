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
from processes.config import get_config
from processes.handlers.session import load_session
from processes.utils import load_reclass_table
from processes.utils.wfs import clipfromwfs_cql
from processes.utils.vector import ensure_metric
from processes.utils.geoserver import filtervectorbyvector, createvieweroutput, republish_layer
from processes.utils.raster import (
    lare_raster,
    aggregate_hazard,
    aggregate_raster_pixel_count_to_hexagons,
)

logger = logging.getLogger(__name__)


def _require_uomgpkg(sessiondir, sessionid: str, archetype: str) -> str:
    """Build and validate the expected UoM GeoPackage path."""
    uomgpkg = str(sessiondir / f'hexagons_{archetype}_{sessionid}.gpkg')
    if not os.path.isfile(uomgpkg):
        raise FileNotFoundError(f'Hexagon file not found: {uomgpkg}')
    return uomgpkg


def _resolve_kcs_layer(cfg, kcs: str) -> tuple[str, str]:
    """Resolve KCS key to (layer_name, datatype) from config."""
    for layer_name, datatype in cfg.kcs.items():
        if kcs in layer_name:
            return layer_name, datatype
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
#TODO: in case of vector we will need also an indicator. We need to add this in the app.yml
def aggregate_kcs_uom(outkcs, uomgpkg, sessionid=None):
    if outkcs is None:
        raise RuntimeError("KCS input is None, cannot aggregate to UoM")

    if not isinstance(outkcs, gpd.GeoDataFrame):
        raise RuntimeError(f"KCS input must be a GeoDataFrame, got {type(outkcs)}")

    if outkcs.empty:
        logger.warning("!-- aggregate_kcs_uom: outkcs is empty, writing zero lengths to UoM")

    layer_names = fiona.listlayers(uomgpkg)
    if not layer_names:
        raise RuntimeError(f"No layers found in {uomgpkg}")
    uom_layer = layer_names[0]

    uom = gpd.read_file(uomgpkg, layer=uom_layer, engine='pyogrio')

    if uom.empty:
        raise RuntimeError("UoM dataset is empty")

    # Ensure a stable key exists for merging.
    if 'id' not in uom.columns:
        logger.warning("!-- aggregate_kcs_uom: 'id' column not found in UoM, creating from index")
        uom = uom.reset_index(drop=False).rename(columns={'index': 'id'})

    # Reproject KCS data to UoM CRS when needed.
    if outkcs.crs != uom.crs:
        outkcs = outkcs.to_crs(uom.crs)

    # Work in projected coordinates for meaningful length calculations.
    uom_calc = ensure_metric(uom, 3035)
    outkcs_calc = ensure_metric(outkcs, 3035)

    # Spatial join: keep UoM as left frame so we can aggregate by hexagon id.
    sjoin_result = gpd.sjoin(uom_calc[['id', 'geometry']], outkcs_calc[['geometry']], how='inner', predicate='intersects')

    if sjoin_result.empty:
        aggregated = uom[['id']].copy()
        aggregated['length'] = 0.0
    else:
        kcs_lengths = outkcs_calc.geometry.length
        sjoin_result['length'] = sjoin_result['index_right'].map(kcs_lengths)
        sjoin_result['length'] = sjoin_result['length'].fillna(0)
        aggregated = sjoin_result.groupby('id', as_index=False)['length'].sum()

    if 'length' in uom.columns:
        uom = uom.drop(columns=['length'])

    uom = uom.merge(aggregated, on='id', how='left')
    uom['length'] = uom['length'].fillna(0)

    uom.to_file(uomgpkg, layer=uom_layer, driver='GPKG', mode='w')
    return uomgpkg


def aggregate_kcs_raster_uom(outkcs_tif: str, uomgpkg: str, csv_path: str, kcs: str) -> str:
    """Aggregate raster KCS to UoM as number of selected pixels per hexagon."""
    if not outkcs_tif or not os.path.isfile(outkcs_tif):
        raise FileNotFoundError(f'Raster KCS file not found: {outkcs_tif}')

    layer_names = fiona.listlayers(uomgpkg)
    if not layer_names:
        raise RuntimeError(f"No layers found in {uomgpkg}")
    uom_layer = layer_names[0]

    uom = gpd.read_file(uomgpkg, layer=uom_layer, engine='pyogrio')
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

    uom = aggregate_raster_pixel_count_to_hexagons(outkcs_tif, uom, classes=classes)
    if 'number of pixels' in uom.columns:
        uom = uom.drop(columns=['number of pixels'])
    uom.rename(columns={'aggregated_value': 'number of pixels'}, inplace=True)
    uom['number of pixels'] = uom['number of pixels'].fillna(0)

    uom.to_file(uomgpkg, layer=uom_layer, driver='GPKG', mode='w')
    return uomgpkg



def mainhandler_uomkcs(sessionid, kcs, hazard, archetype):
    cfg = get_config()
    geoserver_url = cfg.ows_base
    wmsurl = cfg.geoserver.url

    sessiondir = load_session(sessionid)
    uomgpkg = _require_uomgpkg(sessiondir, sessionid, archetype)

    #TODO: add the correct hazard layer to the config. E.g drought.
    hazardlayer = cfg.hazard_layers[hazard]
    logger.info('uomkcs: hazard %r -> layer %s', hazard, hazardlayer)

    uom = gpd.read_file(uomgpkg)
    #In this step we are clipping the hazard layer to the UoM.
    hazardtif = _require_hazard_raster(uom, hazardlayer, sessionid)
    #In this step we are readin from the config the KCS layer and the datatype.
    kcslayer, datatype = _resolve_kcs_layer(cfg, kcs)

    if datatype == 'raster':
        outkcs = lare_raster(uom, uom.crs, kcslayer, sessionid=sessionid)
        logger.debug('uomkcs: KCS %r clipped as raster: %s', kcs, outkcs)
        csv_path = os.path.normpath(
            os.path.join(os.path.dirname(__file__), '..', '..', cfg.hazard_clc_scores['archetype'])
        )
        aggregate_kcs_raster_uom(outkcs, uomgpkg, csv_path, kcs)
    elif datatype == 'vector':
        filter_gdf = gpd.GeoDataFrame(geometry=[uom.geometry.unary_union], crs=uom.crs)
        outkcs = filtervectorbyvector(geoserver_url, filter_gdf, filter_gdf.crs, kcslayer, 4326)
        if outkcs is not None and not outkcs.empty:
            logger.info('uomkcs: KCS %r clipped, %d features', kcs, len(outkcs))
            aggregate_kcs_uom(outkcs, uomgpkg, sessionid=sessionid)
        else:
            logger.warning('uomkcs: no features returned for KCS %r', kcs)
    else:
        raise ValueError(f'Unsupported KCS datatype {datatype!r} for {kcs!r}')

    aggregate_hazard(sessionid, hazardtif, archetype)

    layer_name = f'hexagons_{archetype}_{sessionid}_{kcs}'
    republish_layer(f'hexagons_{archetype}_{sessionid}', workspace='tmp', style_name='hazard', layer_name=layer_name)
    return createvieweroutput([layer_name], 'Aggregated KCS', {'uom': 'Aggregated KCS'}, wmsurl)