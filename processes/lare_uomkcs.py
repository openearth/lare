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
from processes.utils_geoserver import publish_gpkg, filtervectorbyvector
from processes.utils_raster import lare_raster


# from utils import read_appyml, tempfile
# from utils_wfs import clipfromwfs_cql
# from utils_wfs import wfs_filter
# from utils_raster import cut_wcs

logging.basicConfig(level=logging.INFO)

def mainhandler_uomkcs(name, kcs, uomlayer, hazardlr):
        
    msg = None

    # check if hazard provided is listed in the list of hazards
    appconfig = read_appyml('app.yml')
    geoserver_url = appconfig['ows']['base']    
    tmpdir = appconfig['sdi']['tmp']['tmpdir']

    # find the layer defined for hazard as well as uomlayer
    try:
        uomgpkg = os.path.join(tmpdir,uomlayer+'.gpgk')
        if not os.path.isfile(uomgpkg):
            logging.error(f'Layer with Unit of Measurements {uomgpkg} not foudn')
        else:
            logging.info(f'{uomgpkg} found and used in further process') 
    except Exception as e:
        logging.error(f'Failed to find {uomlayer} geopackage')

    # similar for hazard layer.
    try:
        hazardtif = os.path.join(tmpdir,hazardlr+'.tif')
        if not os.path.isfile(hazardtif):
            logging.error(f'Layer with hazarddescripiton {hazardtif} not foudn')
        else:
            logging.info(f'{hazardtif} found and used in further process') 
    except Exception as e:
        logging.error(f'Failed to find {hazardtif} tif')


    # the name or even the gdf is not stored anywhere, this could be an improvement
    logging.info("----!!! Derive GeodataFram using: {}".format(name))
    
    try:
        gdf = clipfromwfs_cql(name,'app.yml')
        msg = f'area of gdf for {name} is {str(gdf.area.sum())}'        
    except Exception as e:
        msg = f'nothing found for {name}, {e}'
        return None
    print(msg)


    # first find out what datatype KCS is
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
        return json.dump(msg)


    # clip the kcs, now it gets interesting, because it can be vector or raster data service
    try:
        if datatype == 'raster':
            outkcs = lare_raster(gdf, 4326, kcs)
        elif datatype == 'vector':
            print('! --- do something new :)')
            outkcs = filtervectorbyvector(geoserver_url,gdf,4326,kcslayer,4326)
            # TODO aggregate the outkcs to the uomgpkg
            print('aggregate the outkcs to the uomgpkg')
        if outkcs != None:

            logging.info(f'{kcs} clipped and ready for use as {outkcs}') 
    except Exception as e:
        logging.error(f'Failed to create subset of {kcs} with erro {str(e)}')
    # load raster into array
    #with rasterio.open(outclc) as src:
    #    kcs_array = src.read(1)
    ##    meta = src.meta
    #    src_nodata = src.nodata
