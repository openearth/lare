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
import re
from owslib.fes import PropertyIsLike, And
from owslib.wfs import WebFeatureService
from owslib.etree import etree as ET

from processes.utils import read_appyml

logger = logging.getLogger(__name__)


def _is_numeric_literal(value):
    """Return True when value can be safely used as an unquoted numeric CQL literal."""
    if isinstance(value, (int, float)):
        return True
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    return bool(re.fullmatch(r"-?\d+(\.\d+)?", stripped))


def _to_cql_literal(value):
    """Convert Python value to a safe CQL literal, stripping any existing quotes."""
    # First, strip any existing surrounding quotes (single or double)
    str_value = str(value).strip()
    if (str_value.startswith("'") and str_value.endswith("'")) or \
       (str_value.startswith('"') and str_value.endswith('"')):
        str_value = str_value[1:-1]
    
    # Check if numeric (after quote removal)
    if _is_numeric_literal(str_value):
        return str_value
    
    # Quote and escape for CQL string literal
    safe_value = str_value.replace("'", "''")
    return f"'{safe_value}'"

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


def clipfromwfs_cql(filtervalue, url=None, name_field=None, typename=None):
    """Fetch a GeoDataFrame from a WFS using a CQL equality filter.

    All optional parameters fall back to values from the centralised
    ``get_config()`` when not supplied.

    Args:
        filtervalue: Value to match against *name_field* via CQL.
        url: OWS endpoint URL.  Defaults to config ``ows.wfs_nuts.url``.
        name_field: Attribute column to filter on.  Defaults to config.
        typename: WFS layer name.  Defaults to config.

    Returns:
        GeoDataFrame or None on network / parse failure.
    """
    from processes.config import get_config

    cfg = get_config()
    wfs_nuts = cfg.wfs_nuts

    if url is None:
        url = wfs_nuts.url
    if typename is None:
        typename = wfs_nuts.layer
    if name_field is None:
        name_field = wfs_nuts.name_field

    cql_literal = _to_cql_literal(filtervalue)
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typename": typename,
        "outputFormat": "application/json",
        "cql_filter": f"{name_field} = {cql_literal}",
    }
    logger.info('Requesting WFS: %s', params)
    try:
        r = requests.get(url, params=params)
        r.raise_for_status()
        gdf = gpd.read_file(BytesIO(r.content))
        if gdf.empty:
            logger.warning('Empty result for %s where %s = %s', typename, name_field, filtervalue)
        else:
            logger.info('WFS filter OK: %s %s=%s (%d features)', typename, name_field, filtervalue, len(gdf))
    except Exception:
        logger.exception('WFS request failed for %s', typename)
        gdf = None
    return gdf