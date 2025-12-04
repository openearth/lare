# -*- coding: utf-8 -*-
# Copyright notice
#   --------------------------------------------------------------------
#   Copyright (C) 2020, 2025 Deltares
#       Gerrit Hendriksen, Ioanna Micha
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
import numpy as np
import rasterio
from rasterio.mask import mask
from rasterio.enums import Resampling
from rasterio.warp import calculate_default_transform, reproject

# -----------------------------
# Utility: dtype & nodata helpers
# -----------------------------
def default_nodata(np_dtype):
    if np.issubdtype(np_dtype, np.floating):
        return np.nan
    if np.issubdtype(np_dtype, np.signedinteger):
        return np.iinfo(np_dtype).min
    if np.issubdtype(np_dtype, np.unsignedinteger):
        return np.iinfo(np_dtype).max
    return None


def normalize_dtype(dtype, fallback_np_dtype=None):
    if dtype is None:
        np_dtype = np.dtype(fallback_np_dtype) if fallback_np_dtype is not None else np.dtype('float32')
    elif isinstance(dtype, np.dtype):
        np_dtype = dtype
    elif isinstance(dtype, str):
        dt = dtype.lower()
        if dt in ('int', 'int32'):
            np_dtype = np.dtype('int32')
        elif dt in ('int16', 'int64', 'uint8', 'uint16', 'uint32'):
            np_dtype = np.dtype(dt)
        elif dt in ('float', 'float32'):
            np_dtype = np.dtype('float32')
        elif dt in ('float64',):
            np_dtype = np.dtype('float64')
        else:
            np_dtype = np.dtype(dt)
    else:
        np_dtype = np.dtype(dtype)
    return np_dtype, np_dtype.name

def ensure_nodata_compatible(np_dtype, nodata_value):
    if nodata_value is None:
        return default_nodata(np_dtype)
    if np.issubdtype(np_dtype, np.floating):
        return np.nan if (isinstance(nodata_value, float) and np.isnan(nodata_value)) else float(nodata_value)
    try:
        iv = int(nodata_value)
    except Exception:
        return default_nodata(np_dtype)
    info = np.iinfo(np_dtype)
    return iv if info.min <= iv <= info.max else default_nodata(np_dtype)


# -----------------------------
# 5. Reproject to EPSG:4326
# -----------------------------
def reproject_to_4326(array, meta, dtype='int32', nodata_out=None):
    if array is None or meta is None:
        print('Reprojection skipped: missing array or meta.')
        return None, None
    np_dtype, rio_dtype = normalize_dtype(dtype, fallback_np_dtype=array.dtype)
    if nodata_out is None:
        nodata_out = default_nodata(np_dtype)
    dst_crs = "EPSG:4326"
    src_crs = meta.get('crs')
    src_transform = meta.get('transform')
    src_width = meta.get('width')
    src_height = meta.get('height')
    if src_crs is None or src_transform is None:
        print('Reprojection failed: incomplete metadata.')
        return None, None
    try:
        left, bottom, right, top = rasterio.transform.array_bounds(src_height, src_width, src_transform)
        dst_transform, dst_width, dst_height = calculate_default_transform(
            src_crs, dst_crs, src_width, src_height, left, bottom, right, top
        )
    except Exception as e:
        print('Reprojection not successful (transform calculation):', e)
        return None, None
    reprojected = np.empty((dst_height, dst_width), dtype=np_dtype)
    try:
        reproject(
            source=array,
            destination=reprojected,
            src_transform=src_transform,
            src_crs=src_crs,
            dst_transform=dst_transform,
            dst_crs=dst_crs,
            resampling=Resampling.nearest,
            src_nodata=nodata_out,
            dst_nodata=nodata_out
        )
    except Exception as e:
        print('Reprojection not successful (warp):', e)
        return None, None
    new_meta = meta.copy()
    new_meta.update({
        "crs": dst_crs,
        "transform": dst_transform,
        "width": dst_width,
        "height": dst_height,
        "dtype": rio_dtype,
        "count": 1,
        "nodata": nodata_out
    })
    return reprojected, new_meta

# -----------------------------
# 2. Clip raster with polygon
# -----------------------------
def clip_raster(raster_path, polygon_gdf, nodata=None):
    if polygon_gdf is None:
        print('No polygon provided for clipping.')
        return None, None
    if not os.path.isfile(raster_path):
        print(f'File {raster_path} not found')
        return None, None
    try:
        with rasterio.open(raster_path) as src:
            polygon_geom = [polygon_gdf.geometry.unary_union]
            src_dtype = np.dtype(src.dtypes[0])
            original_nodata = src.nodata if src.nodata is not None else default_nodata(src_dtype)
            nodata_fill = original_nodata if nodata is None else nodata
            out_image, out_transform = mask(src, polygon_geom, crop=True, filled=True, nodata=nodata_fill)
            out_meta = src.meta.copy()
            out_meta.update({
                "height": out_image.shape[1],
                "width": out_image.shape[2],
                "transform": out_transform,
                "count": 1,
                "nodata": original_nodata
            })
    except Exception as e:
        print('Clipping raster failed:', e)
        return None, None
    return out_image[0], out_meta

# -----------------------------
# 6. Save raster
# -----------------------------
def save_raster(array, meta, output_path, dtype=None, cog=False, nodata_out=None):
    if array is None or meta is None:
        print('Save skipped: missing array or meta.')
        return
    np_dtype, rio_dtype = normalize_dtype(dtype, fallback_np_dtype=array.dtype)
    if nodata_out is None:
        nodata_out = ensure_nodata_compatible(np_dtype, meta.get('nodata'))
    out_meta = meta.copy()
    out_meta.update({"dtype": rio_dtype, "count": 1, "nodata": nodata_out})
    if cog:
        out_meta.update({"driver": "COG", "compress": "deflate"})
    else:
        if "driver" not in out_meta:
            out_meta.update({"driver": "GTiff"})
    arr = array.astype(np_dtype, copy=False)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    try:
        with rasterio.open(output_path, "w", **out_meta) as dst:
            dst.write(arr, 1)
        print(f'Raster saved to {output_path} (dtype={rio_dtype}, nodata={nodata_out}, driver={out_meta["driver"]})')
    except Exception as e:
        print(f'Failed to save raster to {output_path}:', e)