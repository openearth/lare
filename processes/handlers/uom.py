# Copyright (C) 2025 Deltares
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
from pathlib import Path
from time import perf_counter

import geopandas as gpd
import numpy as np
from shapely import STRtree
from shapely.geometry import Polygon

from processes.config import get_config
from processes.handlers.session import load_session
from processes.utils.wfs import clipfromwfs_cql
from processes.utils.vector import ensure_metric, is_metric_crs
from processes.utils.geoserver import publish_and_respond

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


def _require_name_field(cfg, layername: str) -> str:
    """Return configured name_field for a layer or raise."""
    name_field = cfg.datasets.get(layername)
    if not name_field:
        raise ValueError(f'Layername {layername} not found in config')
    return name_field


def _load_region_from_wfs(cfg, layername: str, feature_id: str, name_field: str) -> gpd.GeoDataFrame:
    """Fetch region geometry from WFS and ensure at least one feature exists."""
    gdf = clipfromwfs_cql(feature_id, url=cfg.ows_base, name_field=name_field, typename=layername)
    if gdf is None or gdf.empty:
        raise ValueError(f'No features found for {layername} with id={feature_id}')
    return gdf


def mainhandler_uom(sessionid: str, uomsize: int, layername: str, id: str) -> dict:
    t0 = perf_counter()
    cfg = get_config()
    t1 = perf_counter()
    sessiondir = load_session(sessionid)
    t2 = perf_counter()
    name_field = _require_name_field(cfg, layername)
    t3 = perf_counter()
    gdf = _load_region_from_wfs(cfg, layername, id, name_field)
    t4 = perf_counter()
    logger.info('Spatial reference: %s', gdf.crs)

    if not is_metric_crs(gdf.crs):
        t_reproj_start = perf_counter()
        gdf = ensure_metric(gdf, 3035)
        logger.info('Reprojected to EPSG:3035')
        logger.info('perf:lare_uom reproject_seconds=%.3f', perf_counter() - t_reproj_start)
    t_region_write_start = perf_counter()
    gdf.to_file(sessiondir / 'region.gpkg', driver='GPKG')
    t_region_write_end = perf_counter()
    logger.debug('Region area: %.1f', gdf.area.sum())

    hexgrid_path = sessiondir / f'hexagons_{sessionid}.gpkg'
    t_hex_start = perf_counter()
    hexgdf = hexgrid_within(gdf, uomsize)
    t_hex_end = perf_counter()
    t_hex_write_start = perf_counter()
    hexgdf.to_file(hexgrid_path, driver='GPKG')
    t_hex_write_end = perf_counter()
    logger.info('Hexgrid written: %s (%d hexagons)', hexgrid_path, len(hexgdf))

    t_publish_start = perf_counter()
    result = publish_and_respond(
        hexgrid_path,
        'Unit of Measurement',
        {'uom': 'Unit of Measurement'},
    )
    t_publish_end = perf_counter()
    logger.info(
        (
            'perf:lare_uom total_seconds=%.3f config_seconds=%.3f '
            'load_session_seconds=%.3f resolve_name_field_seconds=%.3f '
            'wfs_fetch_seconds=%.3f region_gpkg_write_seconds=%.3f '
            'hexgrid_build_seconds=%.3f hexgrid_gpkg_write_seconds=%.3f '
            'publish_seconds=%.3f hex_count=%d'
        ),
        t_publish_end - t0,
        t1 - t0,
        t2 - t1,
        t3 - t2,
        t4 - t3,
        t_region_write_end - t_region_write_start,
        t_hex_end - t_hex_start,
        t_hex_write_end - t_hex_write_start,
        t_publish_end - t_publish_start,
        len(hexgdf),
    )
    return result
