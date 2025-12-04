# -*- coding: utf-8 -*-
# Copyright notice
#   --------------------------------------------------------------------
#   Copyright (C) 2020, 2025 Deltares
#       Gerrit Hendriksen, Ioanna Micha
#
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

import os
import configparser
from pathlib import Path
import pandas as pd
import tempfile
import shutil
import logging

LOGGER = logging.getLogger("PYWPS")

service_path = Path(__file__).resolve().parent

def read_config(file_name="configuration.txt") -> tuple:
    """Reads the configuration file
    Returns:
        List with configuration
    """

    cf_file = service_path / file_name
    cf = configparser.RawConfigParser()
    cf.read(cf_file)
    # POSTGIS
    host = cf.get("PostGIS", "host")
    user = cf.get("PostGIS", "user")
    psword = cf.get("PostGIS", "pass")
    db = cf.get("PostGIS", "db")
    port = cf.get("PostGIS", "port")
    # GeoServer
    ows_url = cf.get("GeoServer", "ows_url")
    username = cf.get("GeoServer", "username")
    password = cf.get("GeoServer", "password")
    return (
        host,
        user,
        psword,
        db,
        port,
        ows_url,
        username,
        password,
    )


def create_temp_dir(dir):
    # Temporary folder setup
    tmpdir = tempfile.mkdtemp(dir=dir)
    return tmpdir


def delete_tmp_dir(dir):
    try:
        shutil.rmtree(dir)
    except OSError as e:
        LOGGER.info(f"Error: {dir} : {e.sterror}")


# -----------------------------
# 3. Load reclassification table
# -----------------------------
def load_reclass_table(csv_path, lusecol=None, reclasscol=None):
    if not os.path.isfile(csv_path):
        print(f'File {csv_path} not found')
        return None
    try:
        df = pd.read_csv(csv_path, delimiter=';')
    except Exception as e:
        print(f'Failed to read reclassification CSV {csv_path}:', e)
        return None
    if lusecol not in df.columns or reclasscol not in df.columns:
        print(f'Columns "{lusecol}" and/or "{reclasscol}" not found in {csv_path}')
        return None
    return dict(zip(df[lusecol], df[reclasscol]))


# -----------------------------
# 3. Load reclassification table 
#    with classes, to remap continuos data
# -----------------------------
def load_reclass_table_continuasdata(csv_path,clmin='min',clmax='max',clscore='score'):
    df = pd.read_csv(csv_path, sep=';')
    # Ensure numeric types
    df[clmin] = pd.to_numeric(df[clmin])
    df[clmax] = pd.to_numeric(df[clmax])
    df[clscore] = pd.to_numeric(df[clscore], downcast='integer')
    return df
