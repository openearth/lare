# Copyright (C) 2025 Deltares
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
import os
from pathlib import Path
from time import perf_counter

import geopandas as gpd
import numpy as np
import rasterio
from shapely import STRtree
from shapely.geometry import Polygon

from processes.config import get_config
from processes.handlers.session import load_session
from processes.utils.wfs import clipfromwfs_cql
from processes.utils.vector import ensure_metric, is_metric_crs
from processes.utils.geoserver import publish_and_respond
from processes.utils.raster import lare_raster
from processes.utils import load_reclass_table
from processes.handlers.coastal  import _create_coastal_buffer
from processes.handlers.reclass_clc import reclassify_fast

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


# Archetype name → numeric code in landscapearchetype.csv (lac column)
_ARCHETYPE_CODES = {'coastal': 1, 'urban': 2, 'rural': 3, 'mountainous': 4}


def _clip_and_classify_clc(gdf: gpd.GeoDataFrame, archetype: str, sessionid: str) -> str:
    """Clip the CLC raster to *gdf* and reclassify it into landscape archetype codes.

    Uses ``lare_raster`` to clip the CLC layer, then reclassifies pixel values
    from CLC codes to landscape archetype codes (lac) using the archetype CSV
    defined in ``app.yml`` (``hazards.clc_scores.archetype``).  Only pixels whose
    archetype code matches *archetype* are kept; all others are set to nodata.

    Args:
        gdf (GeoDataFrame): Region geometry used to clip the CLC raster.
        archetype (str): Archetype to retain (``'urban'``, ``'rural'``,
            ``'coastal'``, or ``'mountainous'``).
        sessionid (str): Current session identifier.

    Returns:
        str: Path to the output raster with only the matching archetype pixels.

    Raises:
        ValueError: If *archetype* is unknown or the CLC clip/reclassification fails.
    """
    archetype_lower = archetype.lower()
    if archetype_lower not in _ARCHETYPE_CODES:
        raise ValueError(f'Unknown archetype "{archetype}". Expected one of {list(_ARCHETYPE_CODES)}')

    cfg = get_config()

    # 1. Clip CLC raster to the GeoDataFrame extent
    outclc = lare_raster(gdf, 3035, 'clc', sessionid)
    if outclc is None:
        raise ValueError(f'CLC clip failed for session {sessionid}')

    # 2. Load reclassification table: CLC code → landscape archetype code (lac)
    csv_path = os.path.normpath(
        os.path.join(os.path.dirname(__file__), '..', '..', cfg.hazard_clc_scores)
    )
    reclass_dict = load_reclass_table(csv_path, lusecol='clc', reclasscol='lac')
    if reclass_dict is None:
        raise ValueError(f'Failed to load archetype reclass table from {csv_path}')

    # 3. Open CLC raster, reclassify, and mask to the requested archetype
    with rasterio.open(outclc) as src:
        clc_array = src.read(1)
        meta = src.meta.copy()

    archetype_array = reclassify_fast(clc_array, reclass_dict, dtype='int32',
                                      original_nodata=meta.get('nodata'))
    if archetype_array is None:
        raise ValueError(f'Reclassification to archetype codes failed for session {sessionid}')

    # Keep only the target archetype; set everything else to nodata
    target_code = _ARCHETYPE_CODES[archetype_lower]
    nodata_out = 0
    archetype_array[archetype_array != target_code] = nodata_out

    # 4. Save result
    out_path = outclc.replace('clc', f'clc_{archetype_lower}')
    meta.update(dtype='int32', nodata=nodata_out)
    with rasterio.open(out_path, 'w', **meta) as dst:
        dst.write(archetype_array, 1)

    logger.info('Archetype raster written: %s (%s=%d)', out_path, archetype_lower, target_code)
    return out_path


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
    
    #TODO if archetype is coastal, also save a version in 4326 for use in the coastal processor
    archetype = 'urban'
    if archetype == 'coastal':  
        # clip it with the coastal buffer before saving, to reduce file size and speed up processing in the coastal processor
        gdf = _create_coastal_buffer(gdf, buffer=1000, sessionid=sessionid)
    if archetype in ('rural', 'urban'):
        _clip_and_classify_clc(gdf, archetype, sessionid)

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
