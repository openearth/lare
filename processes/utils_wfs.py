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
import json
import yaml
import geopandas as gpd
from owslib.wfs import WebFeatureService
from owslib.fes2 import PropertyIsLike, Filter, PropertyIsEqualTo, And
from owslib.etree import etree
#from owslib.fes import PropertyIsEqualTo, PropertyIsLike, And

# from processes.utils import *
from processes.utils import read_appyml

# from utils import read_appyml


def wfs_filter(app_cfg_path="app.yml",
                        name_contains=None,
                        crs="EPSG:4326"):
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
    wfs = WebFeatureService(url=url, version="2.0.0")

    # Build filters
    filters = []
    if name_contains:
        # Case-insensitive substring match
        filters.append(
            PropertyIsLike(
                propertyname=name_field,
                literal=f"%{name_contains}%",
                wildCard="%",
                singleChar='_',
                escapeChar="\\",
                matchCase=False
            )
        )

    ogc_filter = None
    if len(filters) == 1:
        ogc_filter = filters[0]
    elif len(filters) > 1:
        ogc_filter = And(filters)

    # Request GeoJSON; srsName ensures coordinate axis handling
    resp = wfs.getfeature(
        typename=typename,
        filter=ogc_filter,
        outputFormat="application/json",  # GeoServer supports this
        srsname=crs
    )

    geojson = json.loads(io.BytesIO(resp.read()).getvalue())

    # todo --> apparantly filtering doesn't work....!!!
    agdf = gpd.GeoDataFrame.from_features(geojson)
    gdf = agdf[agdf[f"{name_field}"] == f"{name_contains}"]
    return gdf



def clipfromwfs(wfs,layer,bbx,fn,srs=4326,of='shape-zip'):
    #wfs11 = WebFeatureService(url='http://localhost:8080/geoserver/global/ows?', version='1.1.0',timeout=320)
    wfs11 = WebFeatureService(url=wfs, version='1.1.0',timeout=640)
    try:
        #response = wfs11.getfeature(typename='global:glhymps', bbox=(75,24,78,26),srsname='urn:x-ogc:def:crs:EPSG:4326',outputFormat='shape-zip')   
        response = wfs11.getfeature(typename=layer, bbox=bbx,srsname='urn:x-ogc:def:crs:EPSG:{s}'.format(s=srs),outputFormat=of)   
        if os.path.isfile(fn):
            os.unlink(fn)
        out = open(fn, 'wb')
        out.write(response.read())
        out.close()
        return fn
    except:
        print(' '.join(['error occurred while clipping layer',layer,'from',wfs]))
        return None

