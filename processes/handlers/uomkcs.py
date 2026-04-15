# -*- coding: utf-8 -*-
# Copyright notice
#   --------------------------------------------------------------------
#   Copyright (C) 2026 Deltares
#       Gerrit Hendriksen
#       gerrit.hendriksen@deltares.nl
#
#   This library is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This library is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this library.  If not, see <http://www.gnu.org/licenses/>.
#   --------------------------------------------------------------------
#
# This tool is part of <a href="http://www.OpenEarth.eu">OpenEarthTools</a>.
# OpenEarthTools is an online collaboration to share and manage data and
# programming tools in an open source, version controlled environment.
# Sign up to recieve regular updates of this function, and to contribute
# your own tools.

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
from processes.utils.wfs import clipfromwfs_cql
from processes.utils.vector import ensure_metric
from processes.utils.geoserver import filtervectorbyvector, createvieweroutput, republish_layer
from processes.utils.raster import lare_raster, aggregate_hazard


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

    logging.info("Updated hexagon GeoPackage file saved to: %s", output_gpkg)

def aggregate_kcs_uom(outkcs, uomgpkg, sessionid=None):
    if outkcs is None:
        raise RuntimeError("KCS input is None, cannot aggregate to UoM")

    if not isinstance(outkcs, gpd.GeoDataFrame):
        raise RuntimeError(f"KCS input must be a GeoDataFrame, got {type(outkcs)}")

    if outkcs.empty:
        logging.warning("!-- aggregate_kcs_uom: outkcs is empty, writing zero lengths to UoM")

    layer_names = fiona.listlayers(uomgpkg)
    if not layer_names:
        raise RuntimeError(f"No layers found in {uomgpkg}")
    uom_layer = layer_names[0]

    uom = gpd.read_file(uomgpkg, layer=uom_layer, engine='pyogrio')

    if uom.empty:
        raise RuntimeError("UoM dataset is empty")

    # Ensure a stable key exists for merging.
    if 'id' not in uom.columns:
        logging.warning("!-- aggregate_kcs_uom: 'id' column not found in UoM, creating from index")
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



def mainhandler_uomkcs(sessionid, kcs, hazard, archetype):
    cfg = get_config()
    geoserver_url = cfg.ows_base
    wmsurl = cfg.geoserver.url

    sessiondir = load_session(sessionid)

    uomgpkg = str(sessiondir / f'hexagons_{archetype}_{sessionid}.gpkg')
    if not os.path.isfile(uomgpkg):
        raise FileNotFoundError(f'Hexagon file not found: {uomgpkg}')

    # hazard key already validated against cfg.hazard_layers by UomKcsInputs
    hazardlayer = cfg.hazard_layers[hazard]
    logging.info('uomkcs: hazard %r -> layer %s', hazard, hazardlayer)

    uom = gpd.read_file(uomgpkg)
    hazardtif = lare_raster(uom, 4326, hazardlayer, sessionid)
    if not hazardtif or not os.path.isfile(hazardtif):
        raise RuntimeError(f'Hazard raster not produced for layer {hazardlayer!r}')

    dctkcs = cfg.kcs
    datatype = None
    kcslayer = None
    for k in dctkcs:
        if kcs in k:
            kcslayer = k
            datatype = dctkcs[k]
            break
    if datatype is None:
        raise ValueError(f'KCS {kcs!r} not found in config layers.kcs')

    if datatype == 'raster':
        outkcs = lare_raster(uom, uom.crs, kcs)
        logging.info('uomkcs: KCS %r clipped as raster: %s', kcs, outkcs)
    elif datatype == 'vector':
        filter_gdf = gpd.GeoDataFrame(geometry=[uom.geometry.unary_union], crs=uom.crs)
        outkcs = filtervectorbyvector(geoserver_url, filter_gdf, filter_gdf.crs, kcslayer, 4326)
        if outkcs is not None and not outkcs.empty:
            logging.info('uomkcs: KCS %r clipped, %d features', kcs, len(outkcs))
            aggregate_kcs_uom(outkcs, uomgpkg, sessionid=sessionid)
        else:
            logging.warning('uomkcs: no features returned for KCS %r', kcs)
    else:
        raise ValueError(f'Unsupported KCS datatype {datatype!r} for {kcs!r}')

    aggregate_hazard(sessionid, hazardtif, archetype)

    layer_name = f'hexagons_{archetype}_{sessionid}_{kcs}'
    republish_layer(f'hexagons_{archetype}_{sessionid}', workspace='tmp', style_name='hazard', layer_name=layer_name)
    return createvieweroutput([layer_name], 'Aggregated KCS', {'uom': 'Aggregated KCS'}, wmsurl)