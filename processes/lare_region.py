# -*- coding: utf-8 -*-
# Copyright notice
#   --------------------------------------------------------------------
#   Copyright (C) 2025 Deltares
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
from shapely.geometry import Polygon
import numpy as np

# local
from processes.utils import read_appyml, tempfile
from processes.utils_wfs import clipfromwfs_cql
from processes.utils_vector import transformgdf, is_metric_crs
from processes.utils_geoserver import publish_gpkg, createvieweroutput

# from utils import read_appyml, tempfile
# from utils_wfs import clipfromwfs_cql
# from utils_vector import transformgdf, is_metric_crs
# from utils_raster import cut_wcs

logging.basicConfig(level=logging.INFO)

def mainhandler_region(name):
        
    msg = None

    # check if hazard provided is listed in the list of hazards
    appconfig = read_appyml('app.yml')    
    tmpdir = appconfig['sdi']['tmp']['tmpdir']
    wmsurl = appconfig['sdi']['geoserver']['url']

    try:
        gdf = clipfromwfs_cql(name,'app.yml')
        agpkg = tempfile(tmpdir,'region_','.gpkg')
        logging.info(f'!-- Main handler region: created {agpkg}')
        # save the geodataframe to a geopackage file
        gdf.to_file(agpkg, driver="GPKG")        
        logging.info(f'!-- Main handler region: saved geodataframe to geopackage {agpkg}')
    except Exception as e:
        msg = f'Clipping geodatafram using regionname {name} failed with following error {str(e)}'
        return json.dumps({"error": msg}), 0
    
    # function to calculate the suggested size of the unit of measurement based on the area of the region    
    print(f'!-- region metric or not {str(gdf.crs)}, {is_metric_crs(gdf.crs)}')
    if not is_metric_crs(gdf.crs):
        gdf = transformgdf(gdf, 3035)
        logging.info(f'!-- Main handler region: transformed geodataframe to metric crs EPSG:3035 for area calculation')     
    area = gdf.geometry.area.sum()
    suggested_uom = int(area/1000) # suggest a unit of measurement size that is 1/1000 of the area of the region    
    logging.info(f'!-- Main handler region: suggested size {str(suggested_uom)}')

    # load the data into geoserver
    try:
        wmslay = publish_gpkg(agpkg,workspace='tmp',style_name='region')
        # Extract the timestamp from the published layer name to use as key in jsontitles
        # createvieweroutput splits layer name by '_' and uses parts[1] as the lookup key
        if wmslay:
            layer_name = wmslay[0]  # e.g., 'region_1770987127134176'
            parts = layer_name.split('_')
            if len(parts) >= 2:
                timestamp = parts[1]  # Extract timestamp for jsontitles key
                # Pass the actual region name (e.g., 'Menorca') as the value
                res = createvieweroutput(wmslay, 'Region', {timestamp: name}, wmsurl)
            else:
                # Fallback if layer name doesn't have expected format
                res = createvieweroutput(wmslay, 'Region', {'region': name}, wmsurl)
        else:
            raise RuntimeError("No layers were published from the geopackage")
        logging.info(f'!-- Main handler region: created viewer output {res}')
        return res, suggested_uom
    except Exception as e:
        msg = f"Failed to publish geopackage or create viewer output: {str(e)}"
        logging.error(msg)
        return json.dumps({"error": msg}), 0