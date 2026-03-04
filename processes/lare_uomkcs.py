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

# local
from processes.utils import read_appyml, tempfile
from processes.utils_wfs import clipfromwfs_cql
from processes.utils_vector import transformgdf, is_metric_crs
from processes.utils_geoserver import publish_gpkg, filtervectorbyvector, createvieweroutput
from processes.utils_raster import lare_raster


# from utils import read_appyml, tempfile
# from utils_wfs import clipfromwfs_cql
# from utils_wfs import wfs_filter
# from utils_raster import cut_wcs

logging.basicConfig(level=logging.INFO)

def aggregate_kcs_uom(outkcs,uomgpkg,tmpdir):
    #outkcs = gpd.read_file(outkcs)
    print(type(outkcs))
    print(type(uomgpkg))

    # Check the CRS of both datasets
    print("CRS of outkcs:", outkcs.crs)

    import fiona

    layer_names = fiona.listlayers(uomgpkg)
    if not layer_names:
        raise RuntimeError(f"No layers found in {uomgpkg}")
    uom_layer = layer_names[0]

    uom = gpd.read_file(uomgpkg, layer=uom_layer, engine='pyogrio')
    print("CRS of uomgpkg:", uom.crs)

    # Reproject if necessary
    if outkcs.crs != uom.crs:
        outkcs = outkcs.to_crs(uom.crs)

    # Calculate the length of the geometries in outkcs
    outkcs['length'] = outkcs.geometry.length

    # Perform the spatial join
    aggregated = gpd.sjoin(outkcs, uom, how="inner", predicate='intersects')
    
    logging.info(f"!-- aggregate_kcs_uom: After sjoin, columns available: {list(aggregated.columns)}")

    # Ensure 'length' column exists in aggregated result (sjoin might have dropped it)
    if 'length' not in aggregated.columns:
        logging.warning(f"!-- aggregate_kcs_uom: 'length' column not found after sjoin, will try to recalculate from geometry")
        aggregated['length'] = aggregated.geometry.length

    # Aggregate the data by summing the lengths
    aggregated = aggregated.groupby('index_right').agg({
        'length': 'sum'  # Sum the lengths of the intersecting geometries
    }).reset_index()

    # Fill missing values with 0
    aggregated['length'] = aggregated['length'].fillna(0)

    # Add aggregated statistic as attribute to existing hexagon features
    result = uom.copy()
    length_by_cell = aggregated.set_index('index_right')['length']
    
    # Check if 'length' attribute exists, create it if not (in double precision)
    if 'length' not in result.columns:
        result['length'] = np.float64(0)
    
    # Update length values with aggregated statistics, ensure double precision
    result['length'] = result.index.map(length_by_cell).fillna(0).astype(np.float64)

    # Save back to the same existing layer (overwrite layer contents, keep same layer entry)
    result.to_file(uomgpkg, layer=uom_layer, driver='GPKG', mode='w')

    print("Aggregation complete. Result written to UoM GeoPackage.")
    return uomgpkg



def mainhandler_uomkcs(sessionid, kcs, hazardlr):
        
    msg = None

    # check if hazard provided is listed in the list of hazards
    appconfig = read_appyml('app.yml')
    geoserver_url = appconfig['ows']['base']    
    tmpdir = appconfig['sdi']['tmp']['tmpdir']
    wmsurl = appconfig['sdi']['geoserver']['url']

    # find the layer defined for hazard as well as uomlayer
    # take into account the crs
    tmpdir = os.path.join(tmpdir, sessionid)
    if not os.path.exists(tmpdir):
        error_msg = f'Session directory {tmpdir} not found'
        logging.error(error_msg)
        return json.dumps({'error': error_msg})
    try:
        uomgpkg = os.path.join(tmpdir,f'hexagons_{sessionid}.gpkg')
        if not os.path.isfile(uomgpkg):
            logging.error(f'Layer with Unit of Measurements {uomgpkg} not found')
        else:
            logging.info(f'{uomgpkg} found and used in further process') 
    except Exception as e:
        logging.error(f'Failed to find {uomgpkg} geopackage')

    # similar for hazard layer.
    try:
        hazardtif = os.path.join(tmpdir,hazardlr+'.tif')
        if not os.path.isfile(hazardtif):
            logging.error(f'Layer with hazarddescripiton {hazardtif} not found')
        else:
            logging.info(f'{hazardtif} found and used in further process') 
    except Exception as e:
        logging.error(f'Failed to find {hazardtif} tif')


    # the name or even the gdf is not stored anywhere, this could be an improvement
    logging.info("----!!! Derive GeodataFrame using: {}".format(sessionid))
    regionfile = os.path.join(tmpdir,'region.gpkg')
    gdf = gpd.read_file(regionfile)
    logging.info(f'!-- Spatial reference ID {str(gdf.crs)}')

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
    agguomkcs_publish = None

    try:
        if datatype == 'raster':
            outkcs = lare_raster(gdf, gdf.crs, kcs)
        elif datatype == 'vector':
            outkcs = filtervectorbyvector(geoserver_url,gdf,gdf.crs,kcslayer,4326)
            # TODO aggregate the outkcs to the uomgpkg
            agguomkcs = aggregate_kcs_uom(outkcs,uomgpkg,tmpdir)
            logging.info(f'!-- KCS {kcs} aggregated to hexagons {agguomkcs}')
            # Republish using a new GeoPackage name so GeoServer gets a new datastore/layer
            agguomkcs_publish = os.path.join(tmpdir, f'hexagons_{sessionid}.gpkg')
            shutil.copyfile(agguomkcs, agguomkcs_publish)
        if outkcs != None:

            logging.info(f'{kcs} clipped and ready for use as {outkcs}') 
    except Exception as e:
        logging.error(f'Failed to create subset of {kcs} with erro {str(e)}')

    # load the data into geoserver and return to WPS.
    layer_name = f'hexagons_{sessionid}_{kcs}'
    try:
        if not agguomkcs_publish:
            return json.dumps({'error': 'Aggregated KCS GeoPackage not available for publishing'})
        wmslay = publish_gpkg(agguomkcs_publish, style_name='transport_density',republish=True, layer_name=layer_name)
        res = createvieweroutput(wmslay, 'Aggregated KCS', {'uom':'Aggregated KCS'}, wmsurl)
        return res
    except Exception as e:
        return json.dumps({'error': str(e)})