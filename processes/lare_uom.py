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

# from utils import read_appyml, tempfile
# from utils_wfs import clipfromwfs_cql
# from utils_wfs import wfs_filter
# from utils_raster import cut_wcs

logging.basicConfig(level=logging.INFO)

def hexgrid_within(gdf, area):
    """
    Create a hexagonal grid clipped to the boundary of a polygon.

    gdf_polygon : GeoDataFrame containing exactly 1 polygon (e.g. NUTS3 boundary)
    hex_area    : desired area of each hexagon (same CRS units!)
    """

    # Ensure polygon geometry
    poly = gdf.geometry.unary_union

    # CRS check: needs to be projected (meters)
    if gdf.crs.is_geographic:
        raise ValueError("CRS must be projected (meters). Reproject first, e.g. EPSG:3035 for Europe")

    # Derive edge length from target area
    # area = (3 * sqrt(3) / 2) * edge^2
    edge = np.sqrt((2 * area) / (3 * np.sqrt(3)))

    # Hexagon width and height
    w = 2 * edge
    h = np.sqrt(3) * edge

    minx, miny, maxx, maxy = poly.bounds

    # Generate grid centers
    x = np.arange(minx - w, maxx + w, w * 0.75)
    y = np.arange(miny - h, maxy + h, h)

    hexes = []
    for i, xi in enumerate(x):
        for j, yi in enumerate(y):
            # shift odd rows
            yi_shift = yi + (h / 2 if i % 2 else 0)
            hexagon = Polygon([
                (xi + edge * np.cos(a), yi_shift + edge * np.sin(a))
                for a in np.linspace(0, 2*np.pi, 7)[:-1]
            ])
            # Keep only hexes intersecting polygon
            if hexagon.intersects(poly):
                hexes.append(hexagon)

    return gpd.GeoDataFrame(geometry=hexes, crs=gdf.crs)


def mainhandler_uom(name, area):
        
    msg = None

    # check if hazard provided is listed in the list of hazards
    appconfig = read_appyml('app.yml')    
    tmpdir = appconfig['sdi']['tmp']['tmpdir']
    try:
        gdf = clipfromwfs_cql(name,'app.yml')
    except Exception as e:
        msg = f'Clipping geodatafram using regionname {name} failed with following error {str(e)}'
        return json.dumps(msg)
    print(msg)
    
    try:
        hexgdf = hexgrid_within(gdf, area)
        hexgdf.to_file(os.path.join(tmpdir,"hexgrid.gpkg"), driver="GPKG")
    except Exception as e:
        msg = f"!-- Main handler hazard: Creation of rasters with clip for name {name} failed with error: {str(e)}"
        return json.dumps(msg)