# -*- coding: utf-8 -*-
# Copyright notice
#   --------------------------------------------------------------------
#   Copyright (C) 2026 Deltares
#       Gerrit Hendriksen, Ioanna Micha
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

from pathlib import Path

import geopandas as gpd

from processes.config import get_config


def load_session(sessionid: str) -> Path:
    """Return the session directory path, raising FileNotFoundError if absent."""
    sessiondir = Path(get_config().tmpdir) / sessionid
    if not sessiondir.exists():
        raise FileNotFoundError(f'Session {sessionid} not found')
    return sessiondir


def load_region(sessionid: str) -> tuple[Path, gpd.GeoDataFrame]:
    """Load region.gpkg from the session directory.

    Returns
    -------
    sessiondir : Path
        Path to the session directory.
    gdf : GeoDataFrame
        Contents of region.gpkg.

    Raises
    ------
    FileNotFoundError
        If the session directory or region.gpkg does not exist.
    ValueError
        If region.gpkg is empty.
    """
    sessiondir = load_session(sessionid)
    region_path = sessiondir / 'region.gpkg'
    if not region_path.exists():
        raise FileNotFoundError(f'region.gpkg not found in session {sessionid}')
    gdf = gpd.read_file(region_path)
    if gdf.empty:
        raise ValueError(f'region.gpkg is empty for session {sessionid}')
    return sessiondir, gdf
