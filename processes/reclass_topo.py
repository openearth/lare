#!/usr/bin/env python3

# -*- coding: utf-8 -*-
# Copyright notice
#   --------------------------------------------------------------------
#   Copyright (C) 2025 Deltares
#     Ioanna Micha
#     ioanna.micha@deltares.nl
#     Gerrit Hendriksen
#     gerrit.hendriksen@deltares.nl	
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
import pandas as pd
import numpy as np
from utils import load_reclass_table_continuasdata
from utils_vector import load_polygon_postgis
from utils_raster import clip_raster, normalize_dtype, ensure_nodata_compatible, save_raster, reproject_to_4326

def reclassify_continuous(array, rules_df, dtype='int32', nodata_out=-9999, original_nodata=None):
    out = np.full(array.shape, nodata_out, dtype=dtype)
    # Mask NoData
    mask_nodata = np.isnan(array) if np.issubdtype(array.dtype, np.floating) else np.zeros_like(array, bool)
    if original_nodata is not None:
        mask_nodata |= (array == original_nodata)
    valid_mask = ~mask_nodata
    for _, row in rules_df.iterrows():
        rng_mask = valid_mask & (array >= row['min']) & (array < row['max'])
        out[rng_mask] = int(row['score'])
    return out


def process_raster_postgis(raster_path, sql_query, csv_path, output_path,
                           dtype='int32', crs=None, cog=False,
                           do_reproject=False, nodata=None):
    polygon_gdf = load_polygon_postgis(sql_query, crs)
    if polygon_gdf is None:
        return
    clipped_array, meta = clip_raster(raster_path, polygon_gdf, nodata=nodata)
    if clipped_array is None or meta is None:
        return
    # read the reclass table with default values
    rules_df = load_reclass_table_continuasdata(csv_path)
    np_dtype, _ = normalize_dtype(dtype, fallback_np_dtype=clipped_array.dtype)
    original_nodata = meta.get('nodata')
    nodata_out = ensure_nodata_compatible(np_dtype, original_nodata if nodata is None else nodata)
    reclass_array = reclassify_continuous(clipped_array, rules_df, dtype=np_dtype.name,
                                          nodata_out=nodata_out, original_nodata=original_nodata)
    if reclass_array is None:
        return
    meta.update({"dtype": np_dtype.name, "nodata": nodata_out, "count": 1})
    if do_reproject:
        reclass_array, meta = reproject_to_4326(reclass_array, meta, dtype=np_dtype.name, nodata_out=nodata_out)
        if reclass_array is None or meta is None:
            return
    save_raster(reclass_array, meta, output_path, dtype=np_dtype.name, cog=cog, nodata_out=nodata_out)


def process_raster_postgis(raster_path, sql_query, csv_path, output_path,
                           dtype='int32', crs=None, cog=False,
                           do_reproject=False, nodata=None, ):
    polygon_gdf = load_polygon_postgis(sql_query, crs)
    if polygon_gdf is None:
        return
    clipped_array, meta = clip_raster(raster_path, polygon_gdf, nodata=nodata)
    if clipped_array is None or meta is None:
        return
    rules_df = load_reclass_table_continuasdata(csv_path)
    np_dtype, _ = normalize_dtype(dtype, fallback_np_dtype=clipped_array.dtype)
    original_nodata = meta.get('nodata')
    nodata_out = ensure_nodata_compatible(np_dtype, original_nodata if nodata is None else nodata)
    reclass_array = reclassify_continuous(clipped_array, rules_df, dtype=np_dtype.name,
                                          nodata_out=nodata_out, original_nodata=original_nodata)
    if reclass_array is None:
        return
    meta.update({"dtype": np_dtype.name, "nodata": nodata_out, "count": 1})
    if do_reproject:
        reclass_array, meta = reproject_to_4326(reclass_array, meta, dtype=np_dtype.name, nodata_out=nodata_out)
        if reclass_array is None or meta is None:
            return
    save_raster(reclass_array, meta, output_path, dtype=np_dtype.name, cog=cog, nodata_out=nodata_out)

    # call the procedure to add weights related to hazards
    # need to refine output_path, for now ... remove elevation from it

    basecsv_path = os.path.dirname(csv_path)
    process_and_save_elevation(clipped_array, meta, output_path.replace('elevation',''), basecsv_path, dtype="float32", cog=False)
    

    # Summary stats
    valid_values = reclass_array[reclass_array != nodata_out]
    unique, counts = np.unique(valid_values, return_counts=True)
    summary = pd.DataFrame({'score': unique, 'pixel_count': counts}).merge(
        rules_df[['score', 'descripton']], on='score', how='left'
    )
    print("\nSummary:")
    print(summary)
    return polygon_gdf

def elev_weight_from_csv(elevation_array, hazardparams, nodata=None,
                         apply_to_elevation=True, low_thresh=200, mid_thresh=800):
    """
    Apply hazard-specific elevation weights using a lookup table from a CSV file.

    Parameters:
        elevation_array (np.ndarray): Elevation values.
        hazard (str): Hazard type (must exist in CSV).
        csv_path (str): Path to CSV file with columns: hazard, lowland, midland, upland.
        nodata (float or int, optional): NoData value to preserve.
        apply_to_elevation (bool): Multiply weights by elevation if True.
        low_thresh (float): Threshold for lowland.
        mid_thresh (float): Threshold for midland.

    Returns:
        np.ndarray: Weighted elevation array.
    """

    # Zone masks
    lowland = elevation_array <= low_thresh
    midland = (elevation_array > low_thresh) & (elevation_array <= mid_thresh)
    upland = elevation_array > mid_thresh

    # Get weights for this hazard
    w = hazardparams
    weights = np.zeros_like(elevation_array, dtype=float)
    weights[lowland] = w["lowland"]
    weights[midland] = w["midland"]
    weights[upland] = w["upland"]

    # Apply weights
    result = elevation_array * weights if apply_to_elevation else weights

    # Preserve NoData
    if nodata is not None:
        result = np.where(elevation_array == nodata, nodata, result)

    return result


def process_and_save_elevation(elevation_array, meta, output_path, basecsv_path, dtype=None, cog=False):
    """
    Apply hazard-specific weights and save raster using save_raster().
    """
    # Load hazard weights from CSV
    df = pd.read_csv(os.path.join(basecsv_path,'elevationhazards.csv'))
    weights_table = df.set_index("hazard").to_dict(orient="index")
    print('outputhpath',output_path)

    rascol = {}
    for hazard in weights_table:
        print(f'processing {hazard} specific weights on elevation')
        hazardparams = weights_table[hazard]
        nodata_in = meta.get('nodata')
        weighted_array = elev_weight_from_csv(elevation_array, hazardparams, nodata=None,
                            apply_to_elevation=True, low_thresh=200, mid_thresh=800)
        outname = 'elevation_'+ hazard+'.tif'
        output_raster = os.path.join(output_path,outname)
        print(output_raster)
        rasarry = save_raster(weighted_array, meta, output_raster, dtype=dtype, cog=cog, nodata_out=nodata_in)
        rascol[hazard] = rasarry

def process_slope(raster_slope,
                  raster_aspect, 
                  polygon_gdf, 
                  slope_cap=60.0, 
                  output_path=None, 
                  nodata_slope=None, 
                  nodata_aspect=None,
                  out_dtype="float32", 
                  crs=None,
                  cog=True):
    if polygon_gdf is None:
        return
    if polygon_gdf.crs != crs:
        polygon_gdf = polygon_gdf.to_crs(crs)

    slope, meta = clip_raster(raster_slope, polygon_gdf, nodata=nodata_slope)
    if slope is None or meta is None:
        return

    aspect, meta = clip_raster(raster_aspect, polygon_gdf, nodata=nodata_aspect)
    if slope is None or meta is None:
        return

    # Build NoData mask
    mask_slope = np.isnan(slope) if np.issubdtype(slope.dtype, np.floating) else (slope == nodata_slope if nodata_slope is not None else False)
    mask_aspect = np.isnan(aspect) if np.issubdtype(aspect.dtype, np.floating) else (aspect == nodata_aspect if nodata_aspect is not None else False)
    mask_nodata = mask_slope | mask_aspect

    # Normalize slope
    slope_norm = np.clip(slope / slope_cap, 0.0, 1.0)

    # Aspect to radians
    aspect_rad = np.deg2rad(aspect)
    northness = (np.cos(aspect_rad) + 1.0) / 2.0
    eastness = (np.sin(aspect_rad) + 1.0) / 2.0

    # Apply NoData as NaN
    slope_norm[mask_nodata] = np.nan
    northness[mask_nodata] = np.nan
    eastness[mask_nodata] = np.nan


    output_dir = r"C:\develop\desirmed\pywps-desirmed\tmp"
    os.makedirs(output_dir, exist_ok=True)

    # For slope, northness, eastness
    output_slope = os.path.join(output_dir, "slope_norm.tif")
    output_northness = os.path.join(output_dir, "northness.tif")
    output_eastness = os.path.join(output_dir, "eastness.tif")

    save_raster(slope_norm, meta, output_slope, dtype=out_dtype, cog=cog, nodata_out=nodata_slope)
    save_raster(northness, meta, output_northness, dtype=out_dtype, cog=cog, nodata_out=nodata_slope)
    save_raster(eastness, meta, output_eastness, dtype=out_dtype, cog=cog, nodata_out=nodata_slope)
    return 


if __name__ == "__main__":
    apath = r"C:\geodata\eu"
    csvbasedir = r'C:\develop\desirmed\pywps-desirmed\data'
    output_path = r'C:\develop\desirmed\pywps-desirmed\tmp'
    name = 'Menorca'
    sql_query = f"SELECT geom, nuts_name FROM governance.nuts_2021 WHERE nuts_name = '{name}'"
    dctmitig = {
        'elevation': ('eudem_dem_4258_europe.tif', 'topo_elevationscores.csv', 'int32','4326')
    }
    for mitigation, (out_tif, csv_file, dt,acrs) in dctmitig.items():
        print(f'Processing {mitigation} -> {out_tif}')
        raster_path = os.path.join(apath,out_tif)
        csv_path = os.path.join(csvbasedir, csv_file)
        output_file = os.path.join(output_path, mitigation)
        polygon_gdf = process_raster_postgis(raster_path, sql_query, csv_path, 
                               output_file, dtype=dt, crs=acrs, cog=True,
                               do_reproject=False, nodata=None)


    dctmitslope = {
        'slope'    : ('eudem_slop_3035_europe.tif', 'int32','3035'),
        'aspect'    : ('eudem_aspc_3035_europe.tif', 'int32','3035')
                }
    print(f'Processing {mitigation} -> {out_tif}')
        
    raster_slope = os.path.join(apath,dctmitslope['slope'][0])
    raster_aspect = os.path.join(apath,dctmitslope['aspect'][0])
    
    process_slope(
        raster_slope,
        raster_aspect, 
        polygon_gdf, 
        60, 
        output_path, 
        nodata_slope=None,
        nodata_aspect=None,
        out_dtype=dctmitslope['slope'][1],  # <-- FIXED
        crs=dctmitslope['slope'][2], 
        cog=True)




# ---------------------------
# CLI Argument Parsing
# ---------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reclassify continuous raster data clipped by PostGIS polygon.")
    parser.add_argument("--raster", required=True, help="Path to input raster (GeoTIFF)")
    parser.add_argument("--sql", required=True, help="SQL query to fetch polygon from PostGIS")
    parser.add_argument("--csv", required=True, help="Path to classification CSV")
    parser.add_argument("--output", required=True, help="Path to output raster")
    parser.add_argument("--db_url", required=True, help="PostGIS connection string (e.g., postgresql://user:pass@host:port/db)")
    parser.add_argument("--dtype", default="int32", help="Output data type (default: int32)")
    parser.add_argument("--crs", default=None, help="Target CRS for polygon (optional)")
    parser.add_argument("--cog", action="store_true", help="Convert output to Cloud Optimized GeoTIFF")
    parser.add_argument("--reproject", action="store_true", help="Reproject output to EPSG:4326")
    parser.add_argument("--nodata", type=float, default=None, help="Override NoData value (optional)")
    args = parser.parse_args()

    process_raster_postgis(
        raster_path=args.raster,
        sql_query=args.sql,
        csv_path=args.csv,
        output_path=args.output,
        db_url=args.db_url,
        dtype=args.dtype,
        crs=args.crs,
        cog=args.cog,
        do_reproject=args.reproject,
        nodata=args.nodata
    )
