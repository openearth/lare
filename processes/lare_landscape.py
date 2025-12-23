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

# local
from processes.utils import read_appyml, tempfile
from processes.utils_wfs import wfs_filter
from processes.utils_raster import cut_wcs

# from utils import read_appyml, tempfile
# from utils_wfs import wfs_filter
# from utils_raster import cut_wcs
"""
stepwise approach:
1. retrieve geodataframe from WFS
2.a derive DEM from WCS
2.b create slope, aspect, elevation hazards from the scores
4.a derive CLC from WCS
4.b create varous hazard mitigation rasters from CLC and scores
"""

def landscape_topo(gdf):
    # acquire base data from app.yml
    appconfig = read_appyml('app.yml')
    
    # get url and layer
    base = appconfig['ows']['base']
    layer = appconfig['layers']['dem']

    tmpdir = appconfig['sdi']['tmp']['tmpdir']
    outfname = tempfile(tmpdir,'dem_','.tif')

    # create tuple object from extent
    xmin, ymin, xmax, ymax = gdf.total_bounds
    dem = cut_wcs(float(xmin), float(ymin), float(xmax), float(ymax), layer, base, outfname, crs=3035, all_box=True)

    return dem


def mainhandler(name):
    msg = None
    # step 1 retrieve GeoDataFrame from WFS
    try:
        gdf = wfs_filter('app.yml',name_contains=name,crs='EPSG:3035')
        msg = f'area of gdf for {name} is {str(gdf.area.sum())}'        
    except Exception as e:
        msg = f'nothing found for {name}, {e}'
    finally:
        print(msg)

    # step 2, clip dem using extent of Geodataframe
    dem = landscape_topo(gdf)
    
    
    return msg



