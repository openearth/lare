#!/usr/bin/env python3
# Copyright (C) 2025 Deltares
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import xarray as xr
import numpy as np
from processes.utils.vector import load_polygon_postgis
from processes.utils import load_reclass_table
from processes.utils.raster import default_nodata, clip_raster, normalize_dtype, ensure_nodata_compatible
from processes.utils.raster import save_raster, reproject_to_4326, build_and_save_stack_from_list


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
                           do_reproject=False, nodata=None, return_da=True):

    polygon_gdf = load_polygon_postgis(sql_query, crs)
    if polygon_gdf is None:
        return None
    clipped_array, meta = clip_raster(raster_path, polygon_gdf, nodata=nodata)
    if clipped_array is None or meta is None:
        return None
    reclass_dict = load_reclass_table(csv_path, lusecol, reclasscol)
    if reclass_dict is None:
        return None

    np_dtype, _ = normalize_dtype(dtype, fallback_np_dtype=clipped_array.dtype)
    original_nodata = meta.get('nodata')
    nodata_out = ensure_nodata_compatible(np_dtype, original_nodata if nodata is None else nodata)

    reclass_array = reclassify_fast(
        clipped_array,
        reclass_dict,
        dtype=np_dtype.name,
        nodata_out=nodata_out,
        original_nodata=original_nodata
    )
    if reclass_array is None:
        return None

    # Update meta for saving
    meta.update({"dtype": np_dtype.name, "nodata": nodata_out, "count": 1})

    # Optional reprojection
    if do_reproject:
        reclass_array, meta = reproject_to_4326(
            reclass_array, meta, dtype=np_dtype.name, nodata_out=nodata_out
        )
        if reclass_array is None or meta is None:
            return None

    # Save to disk (COG or GTiff depending on flag)
    save_raster(reclass_array, meta, output_path, dtype=np_dtype.name, cog=cog, nodata_out=nodata_out)

    if not return_da:
        # keep old behavior
        return reclass_array

    # --- Build an xarray.DataArray with spatial metadata ---
    # meta should have: transform, crs, width, height
    height, width = meta["height"], meta["width"]
    if reclass_array.shape != (height, width):
        raise ValueError(
            f"Array shape {reclass_array.shape} doesn't match meta (height={height}, width={width})."
        )

    # Create coordinate vectors from affine transform
    transform = meta["transform"]  # affine
    crs = meta.get("crs", None)

    # x coords are centers of pixels: x = col * a + x0 + a/2 (for positive scale)
    # Using rasterio convention: transform * (col, row) gives upper-left corner of pixel (x_ul, y_ul).
    # For coords, rioxarray typically uses y from top to bottom; we adopt the same orientation as saved raster.
    cols = np.arange(width)
    rows = np.arange(height)

    x_coords = transform.c + cols * transform.a + transform.a / 2.0
    y_coords = transform.f + rows * transform.e + transform.e / 2.0

    # Build DataArray
    da = xr.DataArray(
        reclass_array,
        dims=("y", "x"),
        coords={"y": y_coords, "x": x_coords},
        name="reclass"
    )
    
    if "band" in da.dims and da.sizes.get("band",1) == 1:
        da = da.squeeze("band", drop=True)

    # Attach CRS, transform, nodata
    da = da.rio.write_crs(crs, inplace=False)
    da = da.rio.write_transform(transform, inplace=False)
    da = da.rio.write_nodata(nodata_out, inplace=False)

    return da



# -----------------------------
# Example batch usage
# -----------------------------
if __name__ == "__main__":
    raster_path = r"C:\geodata\eu_landuse\U2018_CLC2018_V2020_20u1_cog.tif"
    csvbasedir = r'C:\develop\lare\data'
    output_path = r'C:\develop\lare\tmp'
    name = 'Oeste'
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

    # collect the arrays in a list
    arrays = []
    lstnames =[]
    for mitigation, (out_tif, csv_file, dt) in dctmitig.items():
        print(f'Processing {mitigation} -> {out_tif}')
        csv_path = os.path.join(csvbasedir, csv_file)
        output_file = os.path.join(output_path, out_tif)

        if mitigation != 'lusearchetype':
            da = process_raster_postgis(
                raster_path, sql_query, csv_path, lusecol, reclasscol,
                output_file, dtype=dt, crs=3035, cog=True,
                do_reproject=False, nodata=None, return_da=True  # <-- now returns DataArray
            )

            if da is not None:
                arrays.append(da)
                lstnames.append(mitigation)
            else:
                print(f"Warning: {mitigation} produced no data.")

    # Then stack with the list-accepting function we built earlier
    stack = build_and_save_stack_from_list(
        arrays,
        output_path=os.path.join(output_path, "nbs_hotspots.tif"),
        band_names=lstnames,  # optional
        nodata=np.nan,
        compress="DEFLATE",
        tiled=True,
        windowed=True,
        save_each_band=True,
        per_band_dir=os.path.join(output_path, "per_band"),
        per_band_dtype=None,
        per_band_cog=False,
        strict_check=True,
    )




