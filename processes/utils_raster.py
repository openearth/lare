# -*- coding: utf-8 -*-
# Copyright notice
#   --------------------------------------------------------------------
#   Copyright (C) 2018 Deltares
#       Joan Sala
#       joan.salacalero@deltares.nl
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

# $HeadURL: https://svn.oss.deltares.nl/repos/openearthtools/trunk/python/applications/wps/ri2de/processes/utils_raster.py $
# $Keywords: $

import os
import glob
import numpy as np
import rasterio
from scipy.ndimage import grey_dilation
from rasterio.io import MemoryFile
from rasterio.warp import calculate_default_transform, reproject, Resampling
from rasterio.transform import Affine

from processes.utils_wcs import *
from processes.utils_vector import *

# from utils_wcs import *
# from utils_vector import *


#from scipy.misc import imresize  # image resampling

#from osgeo import osr
#from osgeo import gdalconst
#import cv2  # dilate band


import logging

logging.basicConfig(level=logging.INFO)

# Cut a raster layer
def cut_wcs(xst, yst, xend, yend, layername, owsurl, outfname, crs=4326, all_box=False):

    logging.info("----!!! layername: {}, owsurl: {}".format(layername, owsurl,xst,yst))
    linestr = "LINESTRING ({} {}, {} {})".format(xst, yst, xend, yend)
    l = LS(linestr, crs, owsurl, layername)
    l.line()
    l.getraster(outfname, all_box=all_box)
    l = None
    logging.info("Writing: {}".format(outfname))


def utm_epsg_for_lonlat(lon: float, lat: float) -> int:
    """
    Return the EPSG code for the UTM zone at (lon, lat).
    Northern hemisphere: EPSG:326xx; Southern: EPSG:327xx.
    """
    zone = int((lon + 180) // 6) + 1
    if lat >= 0:
        return 32600 + zone
    else:
        return 32700 + zone


def reproject_to_utm_if_geographic(src_ds: rasterio.io.DatasetReader):
    """
    If the source dataset is in a geographic CRS (degrees), reproject to UTM.
    Returns (dataset, was_reprojected). Uses an in-memory dataset to avoid temp files.
    """
    crs = src_ds.crs
    if crs is None or not crs.is_geographic:
        return src_ds, False

    # Get approximate centroid
    bounds = src_ds.bounds
    lon = (bounds.left + bounds.right) / 2.0
    lat = (bounds.top + bounds.bottom) / 2.0

    utm_epsg = utm_epsg_for_lonlat(lon, lat)
    dst_crs = rasterio.crs.CRS.from_epsg(utm_epsg)

    # Compute target transform/shape (keep similar resolution)
    transform, width, height = calculate_default_transform(
        src_ds.crs, dst_crs, src_ds.width, src_ds.height, *src_ds.bounds
    )

    # Prepare destination profile
    dst_profile = src_ds.profile.copy()
    dst_profile.update({
        "crs": dst_crs,
        "transform": transform,
        "width": width,
        "height": height,
        "dtype": "float32",
        "nodata": src_ds.nodata if src_ds.nodata is not None else -9999.0,
        "compress": "deflate"
    })

    # Reproject in-memory
    with MemoryFile() as memfile:
        with memfile.open(**dst_profile) as dst_ds:
            reproject(
                source=rasterio.band(src_ds, 1),
                destination=rasterio.band(dst_ds, 1),
                src_transform=src_ds.transform,
                src_crs=src_ds.crs,
                dst_transform=transform,
                dst_crs=dst_crs,
                resampling=Resampling.bilinear,
                dst_nodata=dst_profile["nodata"],
            )
        # Re-open for reading
        reprojected_ds = memfile.open()
        return reprojected_ds, True


def slope_aspect_from_array(z: np.ndarray, transform: Affine, slope_unit: str = "degree",
                            nodata: float = None):
    """
    Compute slope and aspect from an elevation array and its affine transform.
    - z: 2D numpy array of elevations (float32/float64). NoData should be np.nan or a numeric nodata value.
    - transform: rasterio Affine for pixel size and orientation.
    - slope_unit: "degree" or "percent".
    - nodata: numeric nodata value (optional). If provided, it will be treated as invalid.
    Returns (slope, aspect) arrays as float32, with nodata where invalid or flat (aspect).
    """

    z = np.array(z, dtype=np.float32)

    # Mask NoData
    if nodata is not None:
        mask_invalid = (z == nodata)
        z = z.astype(np.float32)
        z[mask_invalid] = np.nan
    else:
        mask_invalid = np.isnan(z)

    # Pixel size (map units). For north-up rasters, transform.e is negative.
    xres = transform.a
    yres = transform.e
    x_spacing = float(xres)
    y_spacing = float(abs(yres))  # spacing magnitude; rows increase downward

    # Gradients: np.gradient returns derivative along rows (axis 0) and cols (axis 1)
    # grad_row: derivative in the image downward direction; grad_col: derivative eastward.
    grad_row, grad_col = np.gradient(z, y_spacing, x_spacing)

    # Convert to map-coordinate derivatives:
    # rows increase as Y decreases when north-up (transform.e < 0) -> flip sign to get dZ/dY (northing)
    if yres < 0:  # typical north-up geotiff
        dz_dy = -grad_row
    else:  # south-up (rare)
        dz_dy = grad_row

    dz_dx = grad_col  # columns increase eastward (transform.a > 0 in typical cases)

    # Slope (radians)
    slope_rad = np.arctan(np.hypot(dz_dx, dz_dy))
    slope = np.degrees(slope_rad) if slope_unit.lower() == "degree" else np.tan(slope_rad) * 100.0

    # Aspect: 0=N, 90=E, 180=S, 270=W, clockwise.
    # Standard formula: aspect = atan2(dz_dy, -dz_dx) in degrees; wrap to 0..360.
    aspect = np.degrees(np.arctan2(dz_dy, -dz_dx))
    aspect = np.where(aspect < 0, aspect + 360.0, aspect)

    # Handle invalid pixels: slope/aspect nodata where input invalid
    slope = slope.astype(np.float32)
    aspect = aspect.astype(np.float32)

    # Where slope is zero (flat), set aspect to nodata (undefined)
    flat = (np.isfinite(slope) & (slope == 0.0))
    aspect = np.where(flat, np.nan, aspect)

    # Reapply nodata mask
    slope[mask_invalid] = np.nan
    aspect[mask_invalid] = np.nan

    return slope, aspect


def save_geotiff(path: str, array: np.ndarray, ref_ds: rasterio.io.DatasetReader,
                 nodata_value: float = -9999.0):
    """
    Save array as a single-band GeoTIFF using reference dataset's spatial metadata.
    """
    profile = ref_ds.profile.copy()
    profile.update({
        "count": 1,
        "dtype": "float32",
        "nodata": nodata_value,
        "compress": "deflate"
    })

    # Replace NaN with nodata_value for disk
    out = np.array(array, dtype=np.float32)
    out[np.isnan(out)] = nodata_value

    with rasterio.open(path, "w", **profile) as dst:
        dst.write(out, 1)


def compute_slope_aspect_from_dem(
        dem_path: str,
        slope_out: str,
        aspect_out: str,
        slope_unit: str = "degree",
        auto_reproject_to_utm: bool = True,
        nodata_value: float = -9999.0,):
    """
    High-level function:
    - Opens DEM,
    - Reprojects to UTM if CRS is geographic (degrees),
    - Computes slope & aspect,
    - Saves GeoTIFF outputs.
    """
    if slope_unit.lower() not in ("degree", "percent"):
        raise ValueError("slope_unit must be 'degree' or 'percent'")

    with rasterio.open(dem_path) as src:
        working_ds = src
        was_reprojected = False

        if auto_reproject_to_utm and src.crs and src.crs.is_geographic:
            working_ds, was_reprojected = reproject_to_utm_if_geographic(src)

        z = working_ds.read(1).astype(np.float32)
        nodata = working_ds.nodata

        slope, aspect = slope_aspect_from_array(
            z, working_ds.transform, slope_unit=slope_unit, nodata=nodata
        )

        # Save using the working_ds spatial metadata
        save_geotiff(slope_out, slope, working_ds, nodata_value=nodata_value)
        save_geotiff(aspect_out, aspect, working_ds, nodata_value=nodata_value)

        print(f"Computed slope ({slope_unit}) → {slope_out}")
        print(f"Computed aspect (0–360°, 0=N) → {aspect_out}")
        if was_reprojected:
            print("Note: DEM was reprojected to a UTM CRS for metric derivatives.")
    return