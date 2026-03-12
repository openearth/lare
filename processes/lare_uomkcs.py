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
import json
import yaml
import shutil
from collections import defaultdict
import logging

# imports
import geopandas as gpd
import rasterio
from shapely.geometry import Polygon
import numpy as np
import fiona

# local
from processes.utils import read_appyml, tempfile
from processes.utils_wfs import clipfromwfs_cql
from processes.utils_vector import transformgdf, is_metric_crs
from processes.utils_geoserver import publish_gpkg, filtervectorbyvector, createvieweroutput, republish_layer
from processes.utils_raster import lare_raster, aggregate_hazard


# from utils import read_appyml, tempfile
# from utils_wfs import clipfromwfs_cql
# from utils_wfs import wfs_filter
# from utils_raster import cut_wcs

logging.basicConfig(level=logging.INFO)


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

    print("Updated hexagon GeoPackage file saved to:", output_gpkg)

def aggregate_kcs_uom(outkcs,uomgpkg,tmpdir,sessionid=None):
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
    logging.info(f"!-- aggregate_kcs_uom: CRS outkcs={outkcs.crs}, uom={uom.crs}")

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
    uom_calc = uom
    if not is_metric_crs(uom.crs):
        logging.info("!-- aggregate_kcs_uom: UoM CRS is not metric, using EPSG:3857 for length calculation")
        uom_calc = uom.to_crs(3857)

    outkcs_calc = outkcs
    if not is_metric_crs(outkcs.crs):
        logging.info("!-- aggregate_kcs_uom: KCS CRS is not metric, using EPSG:3857 for length calculation")
        outkcs_calc = outkcs.to_crs(3857)

    # Spatial join: keep UoM as left frame so we can aggregate by hexagon id.
    sjoin_result = gpd.sjoin(uom_calc[['id', 'geometry']], outkcs_calc[['geometry']], how='inner', predicate='intersects')
    logging.info(f"!-- aggregate_kcs_uom: sjoin result has {len(sjoin_result)} intersecting features")

    if sjoin_result.empty:
        logging.info("!-- aggregate_kcs_uom: No intersections found, assigning zero lengths")
        aggregated = uom[['id']].copy()
        aggregated['length'] = 0.0
    else:
        # Compute lengths from the matched KCS geometries referenced by index_right.
        kcs_lengths = outkcs_calc.geometry.length
        sjoin_result['length'] = sjoin_result['index_right'].map(kcs_lengths)
        sjoin_result['length'] = sjoin_result['length'].fillna(0)
        aggregated = sjoin_result.groupby('id', as_index=False)['length'].sum()
        logging.info(f"!-- aggregate_kcs_uom: Summed lengths for {len(aggregated)} hexagons")

    # Merge aggregated statistic back into existing hexagon features.
    if 'length' in uom.columns:
        uom = uom.drop(columns=['length'])

    uom = uom.merge(aggregated, on='id', how='left')
    uom['length'] = uom['length'].fillna(0)
    logging.info("!-- aggregate_kcs_uom: Merged aggregated length into UoM and filled nulls with 0")
    
    # Save back to the same existing layer (overwrite layer contents, keep same layer entry)
    uom.to_file(uomgpkg, layer=uom_layer, driver='GPKG', mode='w')

    print("Aggregation complete. Result written to UoM GeoPackage.")
    return uomgpkg



def mainhandler_uomkcs(sessionid, kcs, hazard, archetype):
        
    msg = None

    # check if hazard provided is listed in the list of hazards
    appconfig = read_appyml('app.yml')
    geoserver_url = appconfig['ows']['base']    
    tmpdir = appconfig['sdi']['tmp']['tmpdir']
    wmsurl = appconfig['sdi']['geoserver']['url']

    # section that check hexagons        
    # find the layer defined for hazard as well as uomlayer
    # take into account the crs
    tmpdir = os.path.join(tmpdir, sessionid)
    if not os.path.exists(tmpdir):
        error_msg = f'!-- uomkcs: Session directory {tmpdir} not found'
        logging.error(error_msg)
        return json.dumps({'error': error_msg})
    try:
        uomgpkg = os.path.join(tmpdir,f'hexagons_{archetype}_{sessionid}.gpkg')
        if not os.path.isfile(uomgpkg):
            logging.error(f'!-- uomkcs: Layer with Unit of Measurements {uomgpkg} not found')
        else:
            logging.info(f'{uomgpkg} found and used in further process') 
    except Exception as e:
        logging.error(f'Failed to find {uomgpkg} geopackage')

    hazard_layers = appconfig.get('hazard_layers')
    if not isinstance(hazard_layers, dict):
        # Backward compatibility: allow direct map in hazards when no nested hazard config exists.
        fallback_hazards = appconfig.get('hazards', {})
        if isinstance(fallback_hazards, dict) and 'hazard' not in fallback_hazards:
            hazard_layers = fallback_hazards
        else:
            hazard_layers = {}

    hazardlayer = hazard_layers.get(hazard)
    if hazardlayer is None:
        msg = f'!--- LARE UOM KCS: Hazard {hazard} not found in app configuration'
        logging.error(msg)
        logging.info(f"!--- LARE UOM KCS: Available hazard layer keys: {list(hazard_layers.keys())}")
        return json.dumps({'error': msg})
    else:
        logging.info(f'!--- LARE UOM KCS: Hazard {hazard} found in app configuration with layers {hazardlayer}')
    
    # based on the hazard layer name, clip the hazard layer from the geoserver to the region of interest, this is needed for the next step where the kcs data is clipped to the same region and then aggregated to the hexagons.
    uom = gpd.read_file(uomgpkg)
    try:
        hazardtif = lare_raster(uom, 4326, hazardlayer, sessionid)
        if not os.path.isfile(hazardtif):
            logging.error(f'Layer with hazarddescripiton {hazardtif} not found')
        else:
            logging.info(f'{hazardtif} found and used in further process') 
    except Exception as e:
        logging.error(f'Failed to find {hazardtif} tif')

    # first find out what datatype KCS is, for rasters we need a different approach 
    # than for vector data, because of the aggregation step to the hexagons. 
    # For raster data we can directly cut the raster to the region of interest, 
    # for vector data we need to do a spatial join and aggregate the intersecting geometries to the hexagons.

    dctkcs = appconfig['layers']['kcs']
    datatype = None
    for k in dctkcs.keys():
        if k.find(kcs) != -1:
            kcslayer = k
            datatype = dctkcs[k]
            print('kcslayer',k)
            msg = f'!--- LARE UOM KCS: Datatype for Key community system {kcs} is {datatype}'
            logging.info(msg)
    if datatype == None:
        msg = f'!--- LARE UOM KCS: Datatype for Key community system {kcs} not found'
        return json.dumps({'error': msg})


    # clip the kcs, now it gets interesting, because it can be vector or raster data service
    try:
        if datatype == 'raster':
            outkcs = lare_raster(uom, uom.crs, kcs)
            logging.info(f'!-- KCS {kcs} clipped as raster: {outkcs}')
        elif datatype == 'vector':
            outkcs = filtervectorbyvector(geoserver_url, uom, uom.crs, kcslayer, 4326)

            # Check if result is valid (not None and not empty for GeoDataFrames)
            if outkcs is not None and not outkcs.empty:
                logging.info(f'!-- KCS {kcs} clipped to region of interest, result has {len(outkcs)} features')
                agguomkcs = aggregate_kcs_uom(outkcs, uomgpkg, tmpdir, sessionid=sessionid)
                logging.info(f'!-- KCS {kcs} aggregated to hexagons {agguomkcs}')
            else:
                logging.warning(f'No features returned for {kcs}')
        else:
            msg = f'!--- LARE UOM KCS: Unsupported datatype {datatype} for {kcs}'
            logging.error(msg)
            return json.dumps({'error': msg})
    except Exception as e:
        logging.error(f'Failed to create subset of {kcs} with erro {str(e)}')
        return json.dumps({'error': f'Failed to create subset of {kcs}: {str(e)}'})


    aggregate_hazard(sessionid, hazardtif, archetype)
    # from this point on the process needs to assign the hazard data to the hexagons, this is done by loading the aggregated kcs data into geoserver and then creating a viewer output with the new layer. The viewer output is then returned to the WPS process, which can be used in the next step of the LARE process
    # call lare_coastal with the hazard layer and the kcs layer, this will create a new layer with the hazard data assigned to the hexagons, this is done by loading the aggregated kcs data into geoserver and then creating a viewer output with the new layer. The viewer output is then returned to the WPS process, which can be used in the next step of the LARE process

    
    # load the data into geoserver and return to WPS.
    layer_name = f'hexagons_{archetype}_{sessionid}_{kcs}'
    try:
        publish_gpkg(uomgpkg, workspace='tmp', style_name='hazard',layer_name=layer_name)
        # createvieweroutput expects a list of WMS layer names (with workspace prefix)
        wms_layer = f"tmp:{layer_name}"
        res = createvieweroutput([wms_layer], 'Aggregated KCS', {'uom':'Aggregated KCS'}, wmsurl)
        return res
    except Exception as e:
        return json.dumps({'error': str(e)})