# -*- coding: utf-8 -*-
# Copyright notice
#   --------------------------------------------------------------------
#   Copyright (C) 2018 Deltares
#       Ioanna Micha
#       ioanna.micha@deltares.nl
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

# $HeadURL: https://svn.oss.deltares.nl/repos/openearthtools/trunk/python/applications/wps/ri2de/processes/wps_ri2de_custom.py $
# $Keywords: $


import io
import os
import json
import requests
from io import BytesIO
import geopandas as gpd
import logging

# from processes.utils import *
from processes.utils import read_appyml
logging.basicConfig(level=logging.INFO)

# from utils import read_appyml
def wfs_filter(app_cfg_path="app.yml",
                        name_contains=None,
                        crs='4326'):
    """
    Returns a GeoDataFrame filtered from WFS using OGC filters.
    """
    cfg = read_appyml(app_cfg_path)
    base = cfg["ows"]["base"]                  # "https://desirmed.openearth.eu/geoserver/ows"
    wfs_cfg = cfg["ows"]["wfs_nuts"]
    url = wfs_cfg["url"]                       # same as base
    typename = wfs_cfg["layer"]                # "region:nuts_2021"
    name_field = wfs_cfg["name_field"]         # "nuts_name"

    # Instantiate WFS (prefer 2.0.0 if supported)
    try:
        wfs = WebFeatureService(url=url, version="2.0.0")
        logging.info("----!!! wfs_filter: wfs succesfully initialised")
    except Exception as e:
        logging.info("----!!! wfs_filter: wfs not initialised")
        wfs = None
        return None
        
    # Build filters
    filters = []
    if name_contains:
        # Case-insensitive substring match
        filters.append(
            PropertyIsLike(
                propertyname=name_field,
                literal=f"%{name_contains}%",
                wildCard="%",
                singleChar='.',
                escapeChar="!",
                matchCase=False
            )
        )

    ogc_filter = None
    if len(filters) == 1:
        ogc_filter = filters[0]
    elif len(filters) > 1:
        ogc_filter = And(filters)

    # Request GeoJSON; srsName ensures coordinate axis handling
    gdf = None
    # try:
    resp = wfs.getfeature(
        typename=[typename],
        filter=ogc_filter,
        outputFormat="application/json",  # GeoServer supports this
        srsname=f'urn:ogc:def:crs:EPSG::{crs}'
    )
    #geojson = json.loads(resp.read())
    # todo --> apparantly filtering doesn't work....!!!
    agdf = gpd.read_file(BytesIO(resp.content()))
    gdf = agdf[agdf[f"{name_field}"] == f"{name_contains}"]
    logging.info("----!!! wfs_filter: geodataframe from filter for region {}".format(name_contains))
    # except Exception as e:
    #     logging.info("----!!! wfs_filter: wfs filtering not succesful")
    return gdf


def clipfromwfs_cql(filtervalue, app_cfg_path="app.yml",url=None, name_field=None, typename=None):
    """By applying a CQL Filter on the WFS it is possible to aquire a Geodataframe

    Args:
        filtervalue (str): Should be a value to filter the WFS using a CQL Filter
        app_cfg_path (str, optional): Used to derive crucial information if all the following parameters are none. Defaults to "app.yml".
        url (str, optional): If not none, will be used as url of the geoserver (/ows). Defaults to None, in that case url will be derived from app.yml.
        name_field (str, optional): Field to filter on. Defaults to None, in that case name_field will be derived from app.yml.
        typename (str, optional): typename equals to layername of the service provided. Defaults to None, in that case typename will be derived from app.yml.

    Returns:
        Geodataframe : Geodataframe corresponding with the filtered feature based on filtervalue
    """
    cfg = read_appyml(app_cfg_path)

    wfs_cfg = cfg["ows"]["wfs_nuts"]
    if url == None:
        url = wfs_cfg["url"]                       # url of the geoserver https://desirmed.openearth.eu/geoserver/ows
    if typename == None:
        typename = wfs_cfg["layer"]                # "region:nuts_2021"
    if name_field == None:
        name_field = wfs_cfg["name_field"]         # "nuts_name"

    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typename": typename,
        "outputFormat": "application/json",
        "cql_filter": f"{name_field} = {filtervalue}"  # exact match
    }
    
    try:
        r = requests.get(url, params=params)
        r.raise_for_status()
        gdf = gpd.read_file(BytesIO(r.content))
        logging.info(f'!-- succesfull filtering wfs with parameters for layer {typename} and colum/value {name_field} = {filtervalue}')
    except Exception as e:
        logging.info(f'!-- filtering wfs failed, setting geodataframe to none {str(e)}')
        gdf = None    
    return gdf