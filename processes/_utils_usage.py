# -*- coding: utf-8 -*-
"""
Created on Dec 2025

@author: Gerrit Hendriksen

source: https://publicwiki.deltares.nl/pages/viewpage.action?pageId=119046447

"""
from utils_raster import write_array_grid

# Example
out = write_array_grid(
    raster_grid_path="template.tif",
    raster_name="output.tif",
    array=my_array_2d,          # shape must match template
    nodataval=-9999.0,
    output_dtype="float32",     # or 'uint8', 'int16', etc. If omitted, uses array.dtype
    creation_options={
        "predictor": 2,         # helpful for floating-point compression
        "blockxsize": 256,
        "blockysize": 256,
        # "bigtiff": "YES",     # uncomment if >4GB expected
    },
)
