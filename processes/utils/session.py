# Copyright (C) 2025 Deltares
# SPDX-License-Identifier: GPL-3.0-or-later

from pathlib import Path

import geopandas as gpd

from processes.config import get_config


def load_session(session_id: str) -> Path:
    """Return the session directory path, raising FileNotFoundError if absent."""
    session_dir = Path(get_config().tmpdir) / session_id
    if not session_dir.exists():
        raise FileNotFoundError(f'Session {session_id} not found')
    return session_dir


def load_region(session_id: str) -> tuple[Path, gpd.GeoDataFrame]:
    """Load region.gpkg from the session directory.

    Returns
    -------
    session_dir : Path
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
    session_dir = load_session(session_id)
    region_path = session_dir / 'region.gpkg'
    if not region_path.exists():
        raise FileNotFoundError(f'region.gpkg not found in session {session_id}')
    gdf = gpd.read_file(region_path)
    if gdf.empty:
        raise ValueError(f'region.gpkg is empty for session {session_id}')
    return session_dir, gdf
