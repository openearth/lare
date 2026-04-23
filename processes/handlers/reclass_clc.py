#!/usr/bin/env python3
# Copyright (C) 2025 Deltares
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import xarray as xr
import numpy as np
#from processes.utils import load_reclass_table
from processes.utils.raster import default_nodata #, clip_raster, normalize_dtype, ensure_nodata_compatible
#from processes.utils.raster import save_raster, reproject_to_4326, build_and_save_stack_from_list


def coerce_reclass_dict_to_array_dtype(array, reclass_dict):
    """Coerce reclassification dictionary keys to match the array's data type.

    Ensures that keys in the reclassification dictionary are compatible with the
    array's dtype to avoid lookup errors during array indexing.

    Args:
        array (ndarray): Input array whose dtype will be used for key coercion.
        reclass_dict (dict): Dictionary mapping old values to new values for reclassification.

    Returns:
        dict: Dictionary with keys coerced to the array's dtype, or original keys if coercion fails.
    """
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
    """Perform fast reclassification of an array using a lookup table.

    Creates an efficient lookup array to remap array values. Handles nodata values
    by setting them to the output nodata value. This is faster than iterative mapping
    for large arrays.

    Args:
        array (ndarray): Input array to reclassify.
        reclass_dict (dict): Dictionary mapping old values (keys) to new values.
        dtype (str): Output array data type. Defaults to 'int32'.
        nodata_out: Output nodata value; if None, automatically determined from dtype.
        original_nodata: Original nodata value in the input array. Pixels with this
            value will be set to nodata_out in the output.

    Returns:
        ndarray | None: Reclassified array in the specified dtype, or None if input
            is invalid.
    """
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





