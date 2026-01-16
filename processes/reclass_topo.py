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
import rasterio
from processes.utils import load_reclass_table_continousdata,read_appyml
#from processes.utils_vector import load_polygon_postgis
from processes.utils_raster import open_raster, normalize_dtype, ensure_nodata_compatible, save_raster, reproject_to_4326, save_geotiff


def classify_elevation_raster(raster_path, classification_df):
    """
    Classify elevation raster into lowland, midland, and upland based on min and max values.

    Parameters:
    raster_path (str): Path to the input DEM raster
    classification_df (pd.DataFrame): DataFrame containing min, max, and class values
    output_path (str): Path to the output classified raster
    """
    # define outputfile name
    outraster = raster_path.replace('dem','dem_zones')

    # Read the input DEM raster
    with rasterio.open(raster_path) as src:
        dem_array = src.read(1)
        transform = src.transform
        meta = src.meta

    # Create a classified array
    classified_array = np.zeros_like(dem_array, dtype=np.uint8)

    for index, row in classification_df.iterrows():
        min_val = row['min']
        max_val = row['max']
        class_val = row['score']
        classified_array[(dem_array >= min_val) & (dem_array <= max_val)] = class_val

    # Write the classified array to a new raster
    meta.update(dtype=rasterio.uint8)
    with rasterio.open(outraster, 'w', **meta) as dst:
        dst.write(classified_array, 1)
    return outraster

def create_hazard_rasters(raster_path, classification_df):
    """
    Create hazard rasters for flood, erosion, fire, drought, and heat based on min and max values.

    Parameters:
    raster_path (str): Path to the input DEM raster
    classification_df (pd.DataFrame): DataFrame containing min, max, and hazard values
    output_path_prefix (str): Prefix for the output hazard raster paths
    """
    # Read the input DEM raster
    with rasterio.open(raster_path) as src:
        dem_array = src.read(1)
        transform = src.transform
        meta = src.meta

    hazards = ['flood', 'erosion', 'fire', 'drought', 'heat']

    for hazard in hazards:
        hazard_array = np.zeros_like(dem_array, dtype=np.float32)

        for index, row in classification_df.iterrows():
            min_val = row['min']
            max_val = row['max']
            hazard_val = row[hazard]

            mask = (dem_array >= min_val) & (dem_array <= max_val)
            hazard_array[mask] = hazard_val

        output_path = raster_path.replace('dem',f"dem_{hazard}")
        print('hazard tif', output_path)
        meta.update(dtype=rasterio.float32)
        with rasterio.open(output_path, 'w', **meta) as dst:
            dst.write(hazard_array, 1)

def reclassify_continuous(array, rules_df, dtype='int32', nodata_out=-9999, original_nodata=None):
    
    print('reclassify_continuous ',rules_df) 
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

def process_raster(raster_path, csv_path, output_path,
                           dtype='int32', crs=None, cog=False,
                           do_reproject=False, nodata=None, ):
    
    print('process_raster with ',raster_path)
    
    raster_array, meta = open_raster(raster_path, nodata=nodata)
    if raster_array is None or meta is None:
        return
    rules_df = load_reclass_table_continousdata(csv_path)
    np_dtype, _ = normalize_dtype(dtype, fallback_np_dtype=raster_array.dtype)
    original_nodata = meta.get('nodata')
    nodata_out = ensure_nodata_compatible(np_dtype, original_nodata if nodata is None else nodata)
    reclass_array = reclassify_continuous(raster_array, rules_df, dtype=np_dtype.name,
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
    process_and_save_elevation(raster_array, meta, output_path.replace('elevation',''), basecsv_path, dtype="float32", cog=False)

    # Summary stats
    valid_values = reclass_array[reclass_array != nodata_out]
    unique, counts = np.unique(valid_values, return_counts=True)
    summary = pd.DataFrame({'score': unique, 'pixel_count': counts}).merge(
        rules_df[['score', 'descripton']], on='score', how='left'
    )
    print("\nSummary:")
    print(summary)
    return

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
    
# Ensure masked array for consistent mask logic
    elev_ma = np.ma.array(elevation_array, copy=False)

    # Build class masks using np.ma comparisons (masks propagate correctly)
    lowland = elev_ma <= low_thresh
    midland = (elev_ma > low_thresh) & (elev_ma <= mid_thresh)
    upland = elev_ma > mid_thresh

    # Create a weights array as masked, then fill by classes
    weights = np.ma.zeros(elev_ma.shape, dtype=float)
    weights.mask = np.ma.getmaskarray(elev_ma)  # preserve original mask

    # Assign weights per zone
    w_low = float(hazardparams["lowland"])
    w_mid = float(hazardparams["midland"])
    w_up = float(hazardparams["upland"])

    # Use masked indexing (safe for MaskedArray booleans)
    weights = np.ma.where(lowland, w_low, weights)
    weights = np.ma.where(midland, w_mid, weights)
    weights = np.ma.where(upland,  w_up,  weights)

    # Compute result
    if apply_to_elevation:
        result = elev_ma * weights
    else:
        result = weights

    # Augment mask with nodata value if specified (works for numeric nodata)
    if nodata is not None:
        nd_mask = (np.ma.getdata(elev_ma) == nodata)
        # Combine with existing mask
        result.mask = np.ma.getmaskarray(result) | nd_mask

    return result

    # # Zone masks
    # lowland = elevation_array <= low_thresh
    # midland = (elevation_array > low_thresh) & (elevation_array <= mid_thresh)
    # upland = elevation_array > mid_thresh

    # # Get weights for this hazard
    # w = hazardparams
    # weights = np.zeros_like(elevation_array, dtype=float)
    # weights[lowland] = w["lowland"]
    # weights[midland] = w["midland"]
    # weights[upland] = w["upland"]

    # # Apply weights
    # result = elevation_array * weights if apply_to_elevation else weights

    # # Preserve NoData
    # if nodata is not None:
    #     result = np.where(elevation_array == nodata, nodata, result)

    # return result

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
        print('raster_created',output_raster)
        #rasarry = save_raster(weighted_array, meta, output_raster, dtype=dtype, cog=cog, nodata_out=nodata_in)
        write_masked_raster(output_raster, weighted_array, meta, nodata=nodata_in)    
        #rascol[hazard] = rasarry
        rascol[hazard] = weighted_array

def write_masked_raster(out_path, data_ma, profile, nodata=None):
    """
    Write a masked array to a raster file with a coherent profile.

    Parameters
    ----------
    out_path : str
        Output raster path.
    data_ma : np.ma.MaskedArray
        2D or 3D masked array. If 2D, we’ll write as a single band.
    profile : dict
        Base rasterio profile (e.g., from source.meta). Must include height, width, crs, transform.
    nodata : float|int|None
        Desired nodata. If float (NaN), cast to float32 and let NaNs represent nodata.
        If int, cast to an integer dtype and set profile['nodata']=that integer.
    """
    arr = data_ma

    # Decide dtype and how to encode nodata
    if nodata is None:
        # Keep dtype; if masked, rasterio will write masked pixels as 0 unless you set nodata.
        # Safer: use float32 + NaN so mask is preserved as NaN
        dtype = np.float32
        write_arr = arr.astype(dtype)
        # Fill masked pixels with NaN
        write_arr = np.ma.filled(write_arr, np.nan)
        out_nodata = None  # NaN is carried in the data itself for float rasters
    else:
        if isinstance(nodata, float) and np.isnan(nodata):
            dtype = np.float32
            write_arr = arr.astype(dtype)
            write_arr = np.ma.filled(write_arr, np.nan)
            out_nodata = None  # NaN in float data; rasterio nodata can be omitted or set to None
        elif isinstance(nodata, (int, np.integer)):
            # Integer nodata: cast to an integer dtype and fill masked pixels with that value
            dtype = np.int32
            write_arr = arr.astype(dtype)
            write_arr = np.ma.filled(write_arr, int(nodata))
            out_nodata = int(nodata)
        else:
            # non-integer non-NaN nodata -> float32 with that value
            dtype = np.float32
            write_arr = arr.astype(dtype)
            write_arr = np.ma.filled(write_arr, float(nodata))
            out_nodata = float(nodata)

    # Ensure 3D shape (count, height, width)
    if write_arr.ndim == 2:
        write_arr = write_arr[np.newaxis, :, :]

    out_profile = profile.copy()
    out_profile.update({
        "dtype": dtype.name if hasattr(dtype, "name") else str(dtype),
        "count": write_arr.shape[0],
        "height": write_arr.shape[1],
        "width": write_arr.shape[2],
        "nodata": out_nodata
    })

    with rasterio.open(out_path, "w", **out_profile) as dst:
        dst.write(write_arr)
