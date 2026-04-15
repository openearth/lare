# -*- coding: utf-8 -*-
# Copyright notice
#   --------------------------------------------------------------------
#   Copyright (C) 2026 Deltares
#       Gerrit Hendriksen
#       gerrit.hendriksen@deltares.nl
#       Ioanna Micha
#       ioanna.micha@deltares.nl
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
import gc
import json
import logging
from pathlib import Path

# imports
import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.transform import Affine

# local
from processes.config import get_config
from processes.handlers.session import load_region
from processes.utils.raster import aggregate_coastal, lare_raster, reclassify_fast
from processes.utils.wfs import clipfromwfs_cql
from processes.utils.vector import ensure_metric
from processes.utils.geoserver import publish_and_respond, filtervectorbyvector

def mainhandler_coastal(sessionid, hexagons: gpd.GeoDataFrame = None):
    """
    Main entry point for the coastal archetype workflow.

    For a given `sessionid`, this function:
    - loads application configuration from `app.yml` and the region geometry
      from `<tmp>/<sessionid>/region.gpkg`
    - buffers the region to ensure coverage around the area of interest
    - identifies intersecting coastal zone geometries from GeoServer and writes
      them to `<tmp>/<sessionid>/coastal_zone.gpkg`
    - builds a 1 km buffered coastal zone polygon saved as
      `<tmp>/<sessionid>/coastal_zone_1km_buffered.gpkg` and a 100 m raster mask
      saved as `<tmp>/<sessionid>/coastal_zone_raster_100m.tif`
    - clips required input rasters (CLC, DEM, imperviousness) to the buffered
      coastal zone using `lare_raster`, producing session-specific raster files
    - aggregates all coastal information into a hexagon grid written to
      `<tmp>/<sessionid>/hexagons_<sessionid>.gpkg`
    - publishes the resulting hexagon GeoPackage to GeoServer and returns
      the viewer configuration for that published layer.

    Parameters
    ----------
    sessionid : str
        Unique identifier for the current user/session; used to locate
        temporary input/output files and to name GeoServer resources.
    hexagons : GeoDataFrame, optional
        Pre-built hexagon grid for this session (e.g. returned by
        ``hexgrid_within`` in the UoM step).  When supplied the function
        skips reading ``hexagons_<sessionid>.gpkg`` from disk.  If omitted
        the file is read from the session directory as before.

    Returns
    -------
    str
        JSON string with either an error description or the viewer output
        definition created by `createvieweroutput`.
    """

    # Load application configuration and basic paths/URLs for this run
    cfg = get_config()
    geoserver_url = cfg.ows_base

    try:
        sessiondir, gdf = load_region(sessionid)
    except (FileNotFoundError, ValueError) as exc:
        logging.error('!-- Main handler coastal: %s', exc)
        return json.dumps({'error': str(exc)})

    gdf_buffered = ensure_metric(gdf.copy(), 3857)
    try:
        gdf_buffered['geometry'] = gdf_buffered.geometry.buffer(1000)
    except Exception as e:
        error_msg = f"!-- Main handler uom: Failed to buffer region for session {sessionid}: {str(e)}"
        logging.error(error_msg)
        return json.dumps({'error': error_msg})

    coastlayer = cfg.layer_coastline

    # identify if there is a coast in the region, by clipping the coastal zone from wfs and checking if it has any features
    try:
        gdfcoastal_zone = filtervectorbyvector(geoserver_url,gdf_buffered,gdf_buffered.crs,coastlayer,3857)
        if gdfcoastal_zone is None or gdfcoastal_zone.empty:
            error_msg = f"!-- Main handler uom: No coastal zone features found intersecting the region for session {sessionid}. This process is intended for coastal areas. Please provide a valid coastal region."
            logging.error(error_msg)
            return json.dumps({'error': error_msg})
    except Exception as e:
        error_msg = f"!-- Main handler uom: Failed to identify coastal zone for session {sessionid}: {str(e)}"
        logging.error(error_msg)
        return json.dumps({'error': error_msg})
    
    gdfcoastal_zone.to_file(sessiondir / 'coastal_zone.gpkg', driver='GPKG')

    # Create a 100m resolution raster of the coastal zone (buffered coastline intersected with region)
    try:
        # Ensure coastal zone is in metric CRS for buffering
        gdfcoastal_buffered = ensure_metric(gdfcoastal_zone.copy(), 3857)

        gdfcoastal_buffered['geometry'] = gdfcoastal_buffered.geometry.buffer(1000)
        gdfcoastal_buffered.to_file(sessiondir / 'coastal_zone_1km_buffered.gpkg', driver='GPKG')

        # Define raster parameters using the extent of the intersection
        resolution = 100  # 100 meter resolution
        bounds = gdfcoastal_buffered.total_bounds  # (minx, miny, maxx, maxy)
        
        # Calculate raster dimensions
        width = int(np.ceil((bounds[2] - bounds[0]) / resolution))
        height = int(np.ceil((bounds[3] - bounds[1]) / resolution))
        
        # Create affine transform
        transform = Affine.translation(bounds[0], bounds[3]) * Affine.scale(resolution, -resolution)
        
        # Prepare geometries for rasterization
        shapes = [(geom, 1) for geom in gdfcoastal_buffered.geometry]
        
        # Rasterize the coastal zone geometries
        nodata_value = 0
        raster_array = rasterize(
            shapes,
            out_shape=(height, width),
            transform=transform,
            fill=nodata_value,
            default_value=1,
            dtype=rasterio.uint8
        )
        
        # Save the raster to GeoTIFF
        raster_output_path = str(sessiondir / 'coastal_zone_raster_100m.tif')
        
        with rasterio.open(
            raster_output_path,
            'w',
            driver='GTiff',
            height=height,
            width=width,
            count=1,
            dtype=rasterio.uint8,
            transform=transform,
            crs=gdfcoastal_buffered.crs,
            nodata=nodata_value
        ) as dst:
            dst.write(raster_array, 1)
        
    except Exception as e:
        error_msg = f"!-- Main handler coastal: Failed to create coastal zone raster for session {sessionid}: {str(e)}"
        logging.error(error_msg)
        return json.dumps({'error': error_msg})
    
    # clip clc from csw for entire region.gpkg
    # clip Corine Landcover layer from OGC service
    outclc = lare_raster(gdfcoastal_buffered, 3035, 'clc', sessionid)
    if outclc is None:
        error_msg = f"!-- Main handler coastal: Failed to clip Corine Landcover layer for session {sessionid}"
        logging.error(error_msg)
        return json.dumps({'error': error_msg})

    outdem = lare_raster(gdfcoastal_buffered, 4258, 'dem', sessionid)
    if outdem is None:
        error_msg = f"!-- Main handler coastal: Failed to clip DEM layer for session {sessionid}"
        logging.error(error_msg)
        return json.dumps({'error': error_msg})

    outimp = lare_raster(gdfcoastal_buffered, 3035, 'imperviousness', sessionid)
    if outimp is None:
        error_msg = f"!-- Main handler coastal: Failed to clip Imperviousness layer for session {sessionid}"
        logging.error(error_msg)
        return json.dumps({'error': error_msg})


    # Force cleanup of native GDAL/rasterio objects from lare_raster calls
    # before entering aggregate_coastal, to prevent GC-triggered access violations
    gc.collect()

    # Restrict aggregation to hexagons that intersect the 1 km buffered
    # coastal zone, following a QGIS-style "Select by location (intersect)".
    try:
        hex_path = sessiondir / f'hexagons_{sessionid}.gpkg'

        if hexagons is None:
            if not hex_path.exists():
                error_msg = f"!-- Main handler coastal: Hexagon grid not found for session {sessionid} at expected location: {hex_path}"
                logging.error(error_msg)
                return json.dumps({'error': error_msg})
            hexagons = gpd.read_file(hex_path)

        # gdfcoastal_buffered is already in memory from the buffering step above;
        # no need to re-read coastal_zone_1km_buffered.gpkg from disk.
        coastal = gdfcoastal_buffered

        # Ensure both are in the same CRS
        if hexagons.crs != coastal.crs:
            coastal = coastal.to_crs(hexagons.crs)

       
        coastal_union = coastal.unary_union
        hexagons_coastal = hexagons[hexagons.geometry.intersects(coastal_union)]

        if hexagons_coastal.empty:
            error_msg = f"!-- Main handler coastal: No hexagons intersect the 1 km coastal buffer for session {sessionid}"
            logging.error(error_msg)
            return json.dumps({'error': error_msg})

        # Save coastal-only subset to a separate GeoPackage so the original
        # hexagon file (full grid) remains available.
        coastal_hex_path = sessiondir / f'hexagons_coastal_{sessionid}.gpkg'
        hexagons_coastal.to_file(coastal_hex_path, driver="GPKG")

    except Exception as e:
        error_msg = f"!-- Main handler coastal: Failed to derive coastal hexagon subset for session {sessionid}: {str(e)}"
        logging.error(error_msg)
        return json.dumps({'error': error_msg})

    aggregate_coastal(sessionid)
    hexgrid = str(sessiondir / f'hexagons_coastal_{sessionid}.gpkg')

    try:
        return publish_and_respond(
            Path(hexgrid),
            'Unit of Measurement',
            {'uom': 'Unit of Measurement'},
        )
    except Exception as e:
        error_msg = f"!-- Main handler uom: Failed to publish hexagrid to GeoServer: {str(e)}"
        logging.error(error_msg)
        return json.dumps({'error': error_msg})