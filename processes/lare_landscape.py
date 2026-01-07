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

# imports
import geopandas
import logging

# local
from processes.utils import read_appyml, tempfile
from processes.utils_wfs import clipfromwfs_cql
from processes.utils_raster import cut_wcs, compute_slope_aspect_from_dem

# from utils import read_appyml, tempfile
# from utils_wfs import wfs_filter
# from utils_raster import cut_wcs

logging.basicConfig(level=logging.INFO)


"""
stepwise approach:
1. retrieve geodataframe from WFS
2.a derive DEM from WCS
2.b create slope, aspect, elevation hazards from the scores
4.a derive CLC from WCS
4.b create varous hazard mitigation rasters from CLC and scores
"""

def lare_dem(gdf,crs=4258):
    # acquire base data from app.yml
    appconfig = read_appyml('app.yml')
    
    # get url and layer
    base = appconfig['ows']['base']
    layer = appconfig['layers']['dem']

    tmpdir = appconfig['sdi']['tmp']['tmpdir']
    outfname = tempfile(tmpdir,'dem_','.tif')

    # create tuple object from extent
    # the dem is in 4258, so .... 
    gdf = gdf.to_crs(crs)
    xmin, ymin, xmax, ymax = gdf.total_bounds
    logging.info("----!!! lare_dem: {}, {}".format(xmin,xmax))

    dem = None
    try:
        dem = cut_wcs(float(xmin), float(ymin), float(xmax), float(ymax), layer, base, outfname, crs=crs, all_box=True)
        msg = f'successfully created dem {outfname}'
    except Exception as e:
        msg = e
    finally:
        print(msg)
    return outfname


def mainhandler(name):
    msg = None
    # step 1 retrieve GeoDataFrame from WFS
    name = name.split(':')[1].replace('}','')
    logging.info("----!!! Derive GeodataFram using: {}".format(name))
    
    try:
        gdf = clipfromwfs_cql(name,'app.yml')
        msg = f'area of gdf for {name} is {str(gdf.area.sum())}'        
    except Exception as e:
        msg = f'nothing found for {name}, {e}'
        return None
    print(msg)

    # step 2a, clip dem using extent of Geodataframe
    outdem = lare_dem(gdf,4258)
    outslope = outdem.replace('dem','slope')
    outaspect = outdem.replace('dem','aspect')
    
    # step 2b create slope, aspect from the dem
    compute_slope_aspect_from_dem(
        dem_path=outdem,
        slope_out=outslope,
        aspect_out=outaspect,
        slope_unit="degree",           # or "percent"
        auto_reproject_to_utm=False,    # set False if CRS is already metric (e.g., UTM)
        nodata_value=-9999.0)
    
    #step 3 is deriving hazards from dem
    


    return msg

