# -*- coding: utf-8 -*-
# Copyright notice
#   --------------------------------------------------------------------
#   Copyright (C) 2018 Deltares
#       Joan Sala
#       joan.salacalero@deltares.nl
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

# $HeadURL: https://svn.oss.deltares.nl/repos/openearthtools/trunk/python/applications/wps/ri2de/processes/utils_vector.py $
# $Keywords: $

import json
import os
import json
import geopandas as gpd
from shapely.geometry import MultiPolygon, Polygon
import geojson
from sqlalchemy import create_engine
from pyproj import CRS, Proj, transform

# import local functions
from processes.utils_lines import split_line_multiple

# Change XY coordinates general function
def change_coords(px, py, epsgin='epsg:4326', epsgout='epsg:3857'):
    outProj = Proj(init=epsgout)
    inProj = Proj(init=epsgin)
    return transform(inProj, outProj, px, py)

# Explode coordinates
def explode_coords(coords):
    """Explode a GeoJSON geometry's coordinates object and yield coordinate tuples.
    As long as the input is conforming, the type of the geometry doesn't matter."""
    for e in coords:
        if isinstance(e, (float, int)):
            yield coords
            break
        else:
            for f in explode_coords(e):
                yield f

# Get bounds of a feature collection geojson [south, weast, north, east]
def get_area_bounds_fc(cf, geojson_str):
	geo = geojson.loads(geojson_str)
	minxs = []
	maxxs = []
	minys = []
	maxys = []	
	for f in geo['features']:
		x, y = zip(*list(explode_coords(f['geometry']['coordinates'])))
		minxs.append(min(x))
		maxxs.append(max(x))
		minys.append(min(y))
		maxys.append(max(y))

	minx, miny, maxx, maxy = min(minxs), min(minys), max(maxxs), max(maxys)
	area = abs(maxx-minx * maxy-miny)*111139 # degrees to meters approx

	return minx, miny, maxx, maxy, area

# Get bounds of beature
def get_area_bounds(cf, geojson_str):
	f = geojson.loads(geojson_str)
	lon, lat = zip(*list(explode_coords(f['geometry']['coordinates'])))
	px0, py0, px1, py1 = min(lon), min(lat), max(lon), max(lat)
	minx, miny = change_coords(px0, py0, epsgin='epsg:4326', epsgout='epsg:3857')
	maxx, maxy = change_coords(px1, py1, epsgin='epsg:4326', epsgout='epsg:3857')
	area = ((maxx-minx)*(maxy-miny))/1000000.0 # km2
	area_limit = cf.get('Settings', 'area_limit')
	# Check limit
	if area > float(area_limit):
		raise ValueError('The selected area exceeds the maximum capacity for calculations')

	return area

# Transform a GeoJSON feature collection to a MULTIPOLYGON WKT
# transformed to geopandas version, see below
# def geojson_to_wkt(geojson_str):
	# f = geojson.loads(geojson_str)
	# g = ogr.CreateGeometryFromJson(geojson.dumps(f['geometry']))
	# p = (g.ExportToWkt().replace('POLYGON','') + ',')	
	# return 'MULTIPOLYGON ({})'.format(p[:-1])

def geojson_to_wkt_gpd(geojson_str: str) -> str:
    """
    Same behavior as above, but goes through GeoPandas.
    """
    obj = json.loads(geojson_str)

    # Let GeoPandas build geometries from features or bare geometry
    if obj.get("type") in ("Feature", "FeatureCollection"):
        gdf = gpd.GeoDataFrame.from_features(obj if obj["type"] == "FeatureCollection" else [obj])
        if len(gdf) != 1:
            raise ValueError("Input must contain exactly one geometry.")
        geom = gdf.geometry.iloc[0]
    else:
        # Bare Geometry dict
        gdf = gpd.GeoDataFrame(geometry=[gpd.GeoSeries.from_wkt([])])  # placeholder to get a GeoSeries if needed
        from shapely.geometry import shape as shp_shape
        geom = shp_shape(obj)

    # Normalize to MultiPolygon
    if isinstance(geom, Polygon):
        geom = MultiPolygon([geom])
    elif not isinstance(geom, MultiPolygon):
        raise ValueError(f"Expected Polygon or MultiPolygon, got {geom.geom_type}")

    return geom.wkt

def transformgdf(gdf, crsout=3035):
    """
    Transform a GeoDataFrame to EPSG code 3035 (ETRS89-LAEA Europe).

    Parameters:
    gdf (geopandas.GeoDataFrame): The input GeoDataFrame to be transformed.

    Returns:
    geopandas.GeoDataFrame: The transformed GeoDataFrame in EPSG 3035.
    """
    # Ensure the input is a GeoDataFrame
    if not isinstance(gdf, gpd.GeoDataFrame):
        raise ValueError("Input must be a GeoDataFrame")

    # Transform the GeoDataFrame to EPSG 3035
    gdf_transformed = gdf.to_crs(epsg=crsout)

    return gdf_transformed     

def is_metric_crs(crs):
    """
    Check if a given CRS is in a metric system.

    Parameters:
    crs (pyproj.CRS or str): The CRS to check. This can be a pyproj.CRS object or a CRS string (e.g., 'EPSG:4326').

    Returns:
    bool: True if the CRS is in a metric system, False otherwise.
    """
    # Convert the input to a pyproj.CRS object if it's a string
    if isinstance(crs, str):
        crs = CRS.from_string(crs)

    # Get the axis units
    axis_units = crs.axis_info[0].unit_name

    # Check if the units are metric
    metric_units = ['metre', 'meter', 'kilometre', 'kilometer', 'centimetre', 'centimeter', 'millimetre', 'millimeter']

    return axis_units in metric_units

