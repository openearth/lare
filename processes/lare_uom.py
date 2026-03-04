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


def mainhandler_uom(sessionid, uomsize,layername,id):
        
    msg = None

    # check if hazard provided is listed in the list of hazards
    appconfig = read_appyml('app.yml')    
    tmpdir = appconfig['sdi']['tmp']['tmpdir']
    geoserver_url = appconfig['sdi']['geoserver']['url']
    wfs_url = appconfig['ows']['base']
    
    name_field = appconfig['layers']['datasets'].get(layername)
    if not name_field:
        msg = f"Layername {layername} not found in appconfig"
        return json.dumps(msg)
    
    try:
        gdf = clipfromwfs_cql(id,'app.yml',url=wfs_url, name_field=name_field,typename=layername)
        if gdf is None:
            return json.dumps({'error': f'No features found for {layername} with id={id}'})
        logging.info(f'!-- Spatial reference ID {str(gdf.crs)}')
    except Exception as e:
        msg = f'Clipping geodataframe using regionname {id} failed with following error {str(e)}'
        return json.dumps(msg)
    
    # based on sessionid filepath is there
    sessiondir = os.path.join(tmpdir, sessionid)
    if not os.path.exists(sessiondir):
        msg = f'Session directory {sessiondir} not found'
        logging.error(msg)
        return json.dumps(msg)


    # check crs, this should be a metric system (default to 3035)
    try:
        if not is_metric_crs(gdf.crs):
            gdf = transformgdf(gdf, 3035)
            msg = f"!-- Main handler uom: defaulting to 3035 successful"
        else:
            msg = f"!-- Main handler uom: no transformation necessary"
        gdf.to_file(os.path.join(sessiondir,'region.gpkg'), driver="GPKG")
        logging.info(f'!-- {msg}')
    except Exception as e:
        msg = f"!-- Main handler uom: transformation to 3035 failed"
        logging.error(f'!-- {msg}')
    logging.info(f'!-- Area of {name_field} is {gdf.area.sum()}')

    try:
        # create tempfile with session ID to avoid GeoServer naming conflicts
        hexgrid = os.path.join(sessiondir, f'hexagons_{sessionid}.gpkg')
        logging.info(f'!-- Main handler hexagrid created {hexgrid}')
        # create hexagons based on the passed square meters
        hexgdf = hexgrid_within(gdf, uomsize)
        hexgdf.to_file(hexgrid, driver="GPKG")

        logging.info(f'!-- Main handler hexagrid created {hexgrid}')
    except Exception as e:
        msg = f"!-- Main handler uom: Creation of hexagrid for {name_field} failed with error: {str(e)}"
        logging.error(msg)
        
    
    # load the data into geoserver
    try:
        wmslay = publish_gpkg(hexgrid)
        res = createvieweroutput([wmslay], 'Unit of Measurement', {'uom':'Unit of Measurement'}, geoserver_url)
        return res
    except Exception as e:
        return json.dumps(msg)