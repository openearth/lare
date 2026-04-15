# -*- coding: utf-8 -*-
# Copyright notice
#   --------------------------------------------------------------------
#   Copyright (C) 2025 Deltares
#       Ioanna Micha, Gerrit Hendriksen
#       ioanna.micha@deltares.nl, gerrit.hendriksen@deltares.nl
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

import logging
from pathlib import Path

import geopandas as gpd
import numpy as np
from shapely import STRtree
from shapely.geometry import Polygon

from processes.config import get_config
from processes.utils.wfs import clipfromwfs_cql
from processes.utils.vector import transformgdf, is_metric_crs
from processes.utils.geoserver import publish_gpkg, createvieweroutput, GS

logger = logging.getLogger(__name__)


def hexgrid_within(gdf: gpd.GeoDataFrame, area: float) -> gpd.GeoDataFrame:
    """Create a hexagonal grid clipped to the boundary of a polygon.

    Parameters
    ----------
    gdf : GeoDataFrame
        Must contain at least one polygon and use a projected (metric) CRS.
    area : float
        Target area of each hexagon in the same square units as the CRS.
    """
    poly = gdf.geometry.unary_union

    if gdf.crs.is_geographic:
        raise ValueError("CRS must be projected (meters). Reproject first.")

    # edge length from target hex area: area = (3√3 / 2) * edge²
    edge = np.sqrt((2 * area) / (3 * np.sqrt(3)))
    w = 2 * edge
    h = np.sqrt(3) * edge

    minx, miny, maxx, maxy = poly.bounds

    # Vectorised grid centres via meshgrid
    cols = np.arange(minx - w, maxx + w, w * 0.75)
    rows = np.arange(miny - h, maxy + h, h)
    cx, cy = np.meshgrid(cols, rows, indexing='ij')

    # Shift odd columns by half the hex height
    odd = np.arange(len(cols)) % 2 == 1
    cy[odd, :] += h / 2

    # Pre-compute vertex offsets once
    angles = np.linspace(0, 2 * np.pi, 7)[:-1]
    cos_a = edge * np.cos(angles)
    sin_a = edge * np.sin(angles)

    # Build all candidate hexagons
    hexes = [
        Polygon(zip(xi + cos_a, yi + sin_a))
        for xi, yi in zip(cx.ravel(), cy.ravel())
    ]

    # R-tree bulk filter: prunes by bounding box then tests exact intersection
    tree = STRtree(hexes)
    hits = tree.query(poly, predicate='intersects')
    hexes = [hexes[i] for i in hits]

    return gpd.GeoDataFrame(geometry=hexes, crs=gdf.crs)


def mainhandler_uom(sessionid: str, uomsize: int, layername: str, id: str) -> dict:
    cfg = get_config()
    sessiondir = Path(cfg.tmpdir) / sessionid

    if not sessiondir.exists():
        raise FileNotFoundError(f'Session directory {sessiondir} not found')

    name_field = cfg.datasets.get(layername)
    if not name_field:
        raise ValueError(f'Layername {layername} not found in config')

    gdf = clipfromwfs_cql(id, url=cfg.ows_base, name_field=name_field, typename=layername)
    if gdf is None or gdf.empty:
        raise ValueError(f'No features found for {layername} with id={id}')
    logger.info('Spatial reference: %s', gdf.crs)

    if not is_metric_crs(gdf.crs):
        gdf = transformgdf(gdf, 3035)
        logger.info('Reprojected to EPSG:3035')
    gdf.to_file(sessiondir / 'region.gpkg', driver='GPKG')
    logger.info('Region area: %.1f', gdf.area.sum())

    hexgrid_path = sessiondir / f'hexagons_{sessionid}.gpkg'
    hexgdf = hexgrid_within(gdf, uomsize)
    hexgdf.to_file(hexgrid_path, driver='GPKG')
    logger.info('Hexgrid written: %s (%d hexagons)', hexgrid_path, len(hexgdf))

    store_name = f'hexagons_{sessionid}'
    gs = GS(cfg.geoserver.resturl, cfg.geoserver.user, cfg.geoserver.password)
    try:
        gs.delete_layer_and_store('tmp', store_name)
    except Exception:
        logger.debug('Old datastore %s not found (ok on first run)', store_name)

    wmslay = publish_gpkg(str(hexgrid_path))
    return createvieweroutput(
        wmslay,
        'Unit of Measurement',
        {'uom': 'Unit of Measurement'},
        cfg.geoserver.url,
    )
