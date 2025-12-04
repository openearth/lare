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
import geopandas as gpd
#import rasterio
#from rasterio.mask import mask
import pandas as pd
import numpy as np
#from db_utils import createconnectiontodb
from utils_vector import load_polygon_postgis
from utils import load_reclass_table
from utils_raster import default_nodata, clip_raster, normalize_dtype, ensure_nodata_compatible
from utils_raster import save_raster, reproject_to_4326

def coerce_reclass_dict_to_array_dtype(array, reclass_dict):
    arr_type = array.dtype.type
    coerced = {}
    for k, v in reclass_dict.items():
        try:
            coerced[arr_type(k)] = v
        except Exception:
            coerced[k] = v
    return coerced

# -----------------------------
# 4. FAST reclassification using lookup array
# -----------------------------
def reclassify_fast(array, reclass_dict, dtype='int32', nodata_out=None, original_nodata=None):
    if array is None or reclass_dict is None:
        print('Reclassification skipped: missing array or dictionary.')
        return None
    np_dtype = np.dtype(dtype)
    if nodata_out is None:
        nodata_out = default_nodata(np_dtype)
    reclass_dict = coerce_reclass_dict_to_array_dtype(array, reclass_dict)
    max_val = int(array.max()) if array.size > 0 else 0
    lookup = np.full(max_val + 1, nodata_out, dtype=np_dtype)
    for k, v in reclass_dict.items():
        try:
            idx = int(k)
            if 0 <= idx <= max_val:
                lookup[idx] = v
        except ValueError:
            continue
    out = np.take(lookup, array, mode='clip')
    if original_nodata is not None:
        mask_nodata = (array == original_nodata)
        out[mask_nodata] = nodata_out
    return out

# -----------------------------
# MAIN WORKFLOW
# -----------------------------
def process_raster_postgis(raster_path, sql_query, csv_path, lusecol, reclasscol,
                           output_path, dtype='int32', crs=None, cog=False,
                           do_reproject=False, nodata=None):
    polygon_gdf = load_polygon_postgis(sql_query, crs)
    if polygon_gdf is None:
        return
    clipped_array, meta = clip_raster(raster_path, polygon_gdf, nodata=nodata)
    if clipped_array is None or meta is None:
        return
    reclass_dict = load_reclass_table(csv_path, lusecol, reclasscol)
    if reclass_dict is None:
        return
    np_dtype, _ = normalize_dtype(dtype, fallback_np_dtype=clipped_array.dtype)
    original_nodata = meta.get('nodata')
    nodata_out = ensure_nodata_compatible(np_dtype, original_nodata if nodata is None else nodata)
    reclass_array = reclassify_fast(clipped_array, reclass_dict, dtype=np_dtype.name,
                                    nodata_out=nodata_out, original_nodata=original_nodata)
    if reclass_array is None:
        return
    meta.update({"dtype": np_dtype.name, "nodata": nodata_out, "count": 1})
    if do_reproject:
        reclass_array, meta = reproject_to_4326(reclass_array, meta, dtype=np_dtype.name, nodata_out=nodata_out)
        if reclass_array is None or meta is None:
            return
    save_raster(reclass_array, meta, output_path, dtype=np_dtype.name, cog=cog, nodata_out=nodata_out)


# -----------------------------
# Example batch usage
# -----------------------------
if __name__ == "__main__":
    raster_path = r"C:\geodata\eu_landuse\U2018_CLC2018_V2020_20u1_cog.tif"
    csvbasedir = r'C:\develop\desirmed\pywps-desirmed\data'
    output_path = r'C:\develop\desirmed\pywps-desirmed\tmp'
    name = 'Cávado'
    lusecol = 'clc'
    reclasscol = 'score'
    sql_query = f"SELECT geom, nuts_name FROM governance.nuts_2021 WHERE nuts_name = '{name}'"
    dctmitig = {
        'lusearchetype': ('lusearch.tif', 'landscapearchetype.csv', 'int32'),
        'drought':       ('luse_drought.tif', 'droughtmitigation.csv', 'float32'),
        'flood':         ('luse_flood.tif',   'floodmitigation.csv',   'float32'),
        'fire':          ('luse_fire.tif',    'firemitigation.csv',    'float32'),
        'erosion':       ('luse_erosion.tif', 'erosionmitigation.csv', 'float32'),
        'heatwave':      ('luse_heatwave.tif','heatwavemitigation.csv','float32')
    }
    for mitigation, (out_tif, csv_file, dt) in dctmitig.items():
        print(f'Processing {mitigation} -> {out_tif}')
        csv_path = os.path.join(csvbasedir, csv_file)
        output_file = os.path.join(output_path, out_tif)
        process_raster_postgis(raster_path, sql_query, csv_path, lusecol, reclasscol,
                               output_file, dtype=dt, crs=3035, cog=True,
                               do_reproject=False, nodata=None)

