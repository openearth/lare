# -*- coding: utf-8 -*-
# Copyright notice
#   --------------------------------------------------------------------
#   Copyright (C) 2020, 2025 Deltares
#       Gerrit Hendriksen, Ioanna Micha
#       gerrit.hendriksen@deltares.nl, ioanna.micha@deltares.nl
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

import geopandas as gpd
from db_utils import createconnectiontodb

# -----------------------------
# 1. Load polygon
# -----------------------------
def load_polygon_postgis(sql_query, target_crs=None):
    engine = createconnectiontodb()
    try:
        gdf = gpd.read_postgis(sql_query, engine, geom_col='geom')
    except Exception as e:
        print(f'Not able to read from database with query:\n{sql_query}\nError: {e}')
        return None
    if gdf is None or gdf.empty:
        print('Polygon query returned no geometries.')
        return None
    try:
        if target_crs:
            gdf = gdf.to_crs(target_crs)
            print(f'Polygon reprojected to {target_crs}')
    except Exception as e:
        print('Reprojecting polygon failed:', e)
        return None
    print('Polygon loaded.')
    return gdf