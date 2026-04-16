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
from sqlalchemy import create_engine

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


def get_postgis_engine(appconfig):
    """Create a SQLAlchemy engine from the postgis section in app.yml."""
    pg = appconfig['postgis']
    engine = create_engine(
        f"postgresql://{pg['user']}:{pg['password']}@{pg['host']}/{pg['database']}"
    )
    return engine


def get_upstream_basins(basin_id, appconfig):
    """Return a GeoDataFrame with the clicked basin and all its upstream basins.

    Uses a recursive CTE on the HydroBASINS table. A basin is upstream of
    the clicked basin when its next_down equals an already-collected hybas_id.
    """
    engine = get_postgis_engine(appconfig)

    sql = """
        WITH RECURSIVE upstream AS (
            -- anchor: the clicked basin
            SELECT hybas_id, next_down, next_sink, geom
            FROM hydro.hybas_eu_lev12_v1c
            WHERE hybas_id = %(hybas_id)s

            UNION ALL

            -- recursive step: basins whose next_down points into the set
            SELECT h.hybas_id, h.next_down, h.next_sink, h.geom
            FROM hydro.hybas_eu_lev12_v1c h
            JOIN upstream u ON h.next_down = u.hybas_id
        )
        SELECT * FROM upstream;
    """

    gdf = gpd.read_postgis(sql, engine, geom_col="geom", params={"hybas_id": basin_id})
    logging.info(f'!-- get_upstream_basins: found {len(gdf)} upstream basins for {basin_id}')
    return gdf


def mainhandler_basin(session_id, basin_id):

    msg = None

    appconfig = read_appyml('app.yml')
    tmpdir = appconfig['sdi']['tmp']['tmpdir']
    wmsurl = appconfig['sdi']['geoserver']['url']

    try:
        gdf = get_upstream_basins(basin_id, appconfig)
        if gdf.empty:
            msg = f'No basins found for hybas_id {basin_id}'
            logging.error(msg)
            return json.dumps({"error": msg})

        agpkg = tempfile(os.path.join(tmpdir,session_id), 'basin_', '.gpkg')
        logging.info(f'!-- Main handler basin: created {agpkg}')
        gdf.to_file(agpkg, driver="GPKG")
        logging.info(f'!-- Main handler basin: saved {len(gdf)} basins to {agpkg}')
    except Exception as e:
        msg = f'Fetching upstream basins for {basin_id} failed: {str(e)}'
        logging.error(msg)
        return json.dumps({"error": msg})