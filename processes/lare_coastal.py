# -*- coding: utf-8 -*-
# Copyright notice
#   --------------------------------------------------------------------
#   Copyright (C) 2026 Deltares
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
import gc
import json
import yaml
from collections import defaultdict
import pandas as pd
import numpy as np
import logging

# imports
import geopandas as gpd
from shapely.geometry import Polygon
import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.transform import Affine

# local
from processes.config import get_config
from processes.utils_raster import aggregate_coastal, lare_raster, reclassify_fast
from processes.utils_wfs import clipfromwfs_cql
from processes.utils_vector import transformgdf, is_metric_crs
from processes.utils_geoserver import publish_gpkg, createvieweroutput, GS, filtervectorbyvector

def mainhandler_coastal(sessionid):
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

    Returns
    -------
    str
        JSON string with either an error description or the viewer output
        definition created by `createvieweroutput`.
    """

    # Load application configuration and basic paths/URLs for this run
    cfg = get_config()
    geoserver_url = cfg.ows_base
    tmpdir = cfg.tmpdir
    wmsurl = cfg.geoserver.url
    
    # coastal urban archetype always has the same ingredients:
    # - identify region.gpkg
    # - identify if there is a coast!
    # - clip coast from wfs (decide to convert this to polygon, in case reuse in coming steps)
    # - create a raster 1 km inland
    # - clip CLC from csw for entire region.gpkg
    # - clip dem for coastal zone
    # - clip imperviousness for coastal zone
    # - clip population for coastal zone

    regionfile = os.path.join(tmpdir, f'{sessionid}', 'region.gpkg')
    if not os.path.exists(regionfile):
        error_msg = f"!-- Main handler uom: Region file not found for session {sessionid} at expected location: {regionfile}"
        logging.error(error_msg)
        return json.dumps({'error': error_msg})

    gdf = gpd.read_file(regionfile,)
    if gdf.empty:
        error_msg = f"!-- Main handler uom: Region file for session {sessionid} is empty: {regionfile}"
        logging.error(error_msg)
        return json.dumps({'error': error_msg})
    else:
        logging.info(f'!-- Main handler uom: Successfully read region file for session {sessionid} with {len(gdf)} features from {regionfile}')
    
    #buffer the region by 1km
    gdf_buffered = gdf.copy()
    if not is_metric_crs(gdf.crs):
        gdf_buffered = transformgdf(gdf_buffered, 'EPSG:3857')
        logging.info(f'!-- Main handler uom: Transformed region to metric CRS for buffering: {gdf_buffered.crs}')
    try:
        gdf_buffered['geometry'] = gdf_buffered.geometry.buffer(1000)
        logging.info(f'!-- Main handler uom: Successfully buffered region by 1km for session {sessionid}')
    except Exception as e:
        error_msg = f"!-- Main handler uom: Failed to buffer region for session {sessionid}: {str(e)}"
        logging.error(error_msg)
        return json.dumps({'error': error_msg})

    # get coastal zone layer name from app config
    try:
        coastlayer = cfg.layer_coastline
        logging.info(f'!-- Main handler uom: Successfully retrieved coastal zone {coastlayer} layer from app config for session {sessionid}')    
    except KeyError as e:
        error_msg = f"!-- Main handler uom: Failed to get coastal zone layer from app config for session {sessionid}: {str(e)}"
        logging.error(error_msg)
        return json.dumps({'error': error_msg})

    # identify if there is a coast in the region, by clipping the coastal zone from wfs and checking if it has any features
    try:
        gdfcoastal_zone = filtervectorbyvector(geoserver_url,gdf_buffered,gdf_buffered.crs,coastlayer,3857)
        if gdfcoastal_zone is None or gdfcoastal_zone.empty:
            error_msg = f"!-- Main handler uom: No coastal zone features found intersecting the region for session {sessionid}. This process is intended for coastal areas. Please provide a valid coastal region."
            logging.error(error_msg)
            return json.dumps({'error': error_msg})
        logging.info(f'!-- Main handler uom: Successfully identified coastal zone with {len(gdfcoastal_zone)} features for session {sessionid}')
    except Exception as e:
        error_msg = f"!-- Main handler uom: Failed to identify coastal zone for session {sessionid}: {str(e)}"
        logging.error(error_msg)
        return json.dumps({'error': error_msg})
    
    gdfcoastal_zone.to_file(os.path.join(tmpdir, f'{sessionid}',f'coastal_zone.gpkg'), driver='GPKG')

    # Create a 100m resolution raster of the coastal zone (buffered coastline intersected with region)
    try:
        # Ensure coastal zone is in metric CRS for buffering
        if not is_metric_crs(gdfcoastal_zone.crs):
            gdfcoastal_buffered = transformgdf(gdfcoastal_zone, 3857)
            logging.info(f'!-- Main handler coastal: Transformed coastal zone to metric CRS: {gdfcoastal_buffered.crs}')
        else:
            gdfcoastal_buffered = gdfcoastal_zone.copy()
        
        # Buffer the clipped coastline by 1km
        gdfcoastal_buffered['geometry'] = gdfcoastal_buffered.geometry.buffer(1000)
        logging.info(f'!-- Main handler coastal: Successfully buffered clipped coastline by 1km for session {sessionid}')
        gdfcoastal_buffered.to_file(os.path.join(tmpdir, f'{sessionid}', f'coastal_zone_1km_buffered.gpkg'), driver='GPKG')

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
        raster_output_path = os.path.join(tmpdir, f'{sessionid}', 'coastal_zone_raster_100m.tif')
        
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
        
        logging.info(f'!-- Main handler coastal: Successfully created 100m resolution raster at {raster_output_path} for session {sessionid} with dimensions {width}x{height}')
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
    else:
        logging.info(f'!-- Main handler coastal: Successfully clipped Corine Landcover layer for session {sessionid}')

    outdem = lare_raster(gdfcoastal_buffered, 4258, 'dem', sessionid)
    if outdem is None:
        error_msg = f"!-- Main handler coastal: Failed to clip DEM layer for session {sessionid}"
        logging.error(error_msg)
        return json.dumps({'error': error_msg})
    else:   
        logging.info(f'!-- Main handler coastal: Successfully clipped DEM layer for session {sessionid}')   
    
    outimp = lare_raster(gdfcoastal_buffered, 3035, 'imperviousness', sessionid)
    if outimp is None:
        error_msg = f"!-- Main handler coastal: Failed to clip Imperviousness layer for session {sessionid}"
        logging.error(error_msg)
        return json.dumps({'error': error_msg})
    else:
        logging.info(f'!-- Main handler coastal: Successfully clipped Imperviousness layer for session {sessionid}')


    # Force cleanup of native GDAL/rasterio objects from lare_raster calls
    # before entering aggregate_coastal, to prevent GC-triggered access violations
    gc.collect()

    # Restrict aggregation to hexagons that intersect the 1 km buffered
    # coastal zone, following a QGIS-style "Select by location (intersect)".
    try:
        session_dir = os.path.join(tmpdir, f"{sessionid}")
        hex_path = os.path.join(session_dir, f"hexagons_{sessionid}.gpkg")
        coastal_path = os.path.join(session_dir, "coastal_zone_1km_buffered.gpkg")

        if not os.path.exists(hex_path):
            error_msg = f"!-- Main handler coastal: Hexagon grid not found for session {sessionid} at expected location: {hex_path}"
            logging.error(error_msg)
            return json.dumps({'error': error_msg})
        if not os.path.exists(coastal_path):
            error_msg = f"!-- Main handler coastal: Coastal buffer file not found for session {sessionid} at expected location: {coastal_path}"
            logging.error(error_msg)
            return json.dumps({'error': error_msg})

        # Read layers
        hexagons = gpd.read_file(hex_path)
        coastal = gpd.read_file(coastal_path)

        # Ensure both are in the same CRS
        if hexagons.crs != coastal.crs:
            logging.info(f'!-- Main handler coastal: Reprojecting coastal buffer from {coastal.crs} to {hexagons.crs} for intersection with hexagons')
            coastal = coastal.to_crs(hexagons.crs)

       
        coastal_union = coastal.unary_union
        hexagons_coastal = hexagons[hexagons.geometry.intersects(coastal_union)]

        if hexagons_coastal.empty:
            error_msg = f"!-- Main handler coastal: No hexagons intersect the 1 km coastal buffer for session {sessionid}"
            logging.error(error_msg)
            return json.dumps({'error': error_msg})

        # Save coastal-only subset to a separate GeoPackage so the original
        # hexagon file (full grid) remains available.
        coastal_hex_path = os.path.join(session_dir, f'hexagons_coastal_{sessionid}.gpkg')
        hexagons_coastal.to_file(coastal_hex_path, driver="GPKG")
        logging.info(f'!-- Main handler coastal: Saved {len(hexagons_coastal)} coastal hexagons to {coastal_hex_path}')

    except Exception as e:
        error_msg = f"!-- Main handler coastal: Failed to derive coastal hexagon subset for session {sessionid}: {str(e)}"
        logging.error(error_msg)
        return json.dumps({'error': error_msg})

    # call aggregate_coastal(sessionid) on coastal-only hexagons
    logging.info(f'!-- Main handler coastal: Starting aggregation of coastal data for session {sessionid} using coastal hexagon subset')
    aggregate_coastal(sessionid)
    hexgrid = os.path.join(tmpdir,f'{sessionid}',f'hexagons_coastal_{sessionid}.gpkg')

    try:
        # Clean up old layer and datastore before publishing new one
        store_name = f'hexagons_{sessionid}'
        try:
            gs = GS(cfg.geoserver.resturl, cfg.geoserver.user, cfg.geoserver.password)
            # Try to delete old datastore (with recursive=True to delete all layers within it)
            logging.info(f'!-- Attempting to clean up old datastore: {store_name}')
            gs.delete_layer_and_store('tmp', store_name)
        except Exception as cleanup_err:
            logging.warning(f'!-- Cleanup of old datastore failed (may not exist): {str(cleanup_err)}')
        
        # Now publish the new GeoPackage
        wmslay = publish_gpkg(hexgrid)
        res = createvieweroutput(wmslay, 'Unit of Measurement', {'uom':'Unit of Measurement'}, geoserver_url)
        return res
    except Exception as e:
        error_msg = f"!-- Main handler uom: Failed to publish hexagrid to GeoServer: {str(e)}"
        logging.error(error_msg)
        return json.dumps({'error': error_msg})