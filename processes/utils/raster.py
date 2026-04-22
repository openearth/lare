# Copyright (C) 2018 Deltares
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import numpy as np
import rasterio
import xarray as xr
import geopandas as gpd
from scipy.ndimage import grey_dilation
from rasterio.mask import mask
from rasterio.features import rasterize
from rasterio.io import MemoryFile
from rasterio.warp import calculate_default_transform, reproject, Resampling
from rasterio.transform import Affine

from processes.config import get_config
from processes.utils import coerce_reclass_dict_to_array_dtype, tempfile
from processes.utils.wcs import LS
from processes.utils.vector import *

# from processes.utils.wcs import *
# from processes.utils.vector import *


#from scipy.misc import imresize  # image resampling

#from osgeo import osr
#from osgeo import gdalconst
#import cv2  # dilate band


import logging
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


def log_memory_status(stage_name):
    """Log current memory usage at DEBUG level."""
    if HAS_PSUTIL:
        process = psutil.Process()
        memory_info = process.memory_info()
        memory_percent = process.memory_percent()
        logging.debug(f"MEMORY [{stage_name}]: RSS={memory_info.rss / (1024**3):.2f}GB, VMS={memory_info.vms / (1024**3):.2f}GB, Percent={memory_percent:.1f}%")
    else:
        logging.debug(f"MEMORY [{stage_name}]: psutil not available")

logger = logging.getLogger(__name__)

# Cut a raster layer
def cut_wcs(xst, yst, xend, yend, layername, owsurl, outfname, crs=4326, all_box=False):

    linestr = "LINESTRING ({} {}, {} {})".format(xst, yst, xend, yend)
    l = LS(linestr, crs, owsurl, layername)
    l.line()
    l.getraster(outfname, all_box=all_box)
    l = None


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
        dem_norm_out: str,
        dem_eastness: str,
        dem_northness: str,
        slope_unit: str = "degree",
        auto_reproject_to_utm: bool = True,
        nodata_value: float = -9999.0,
        ):
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

        # Normalize slope
        slope_cap = 60 # find out what this means)
        slope_norm = np.clip(slope / slope_cap, 0.0, 1.0)

        # Aspect to radians
        aspect_rad = np.deg2rad(aspect)
        northness = (np.cos(aspect_rad) + 1.0) / 2.0
        eastness = (np.sin(aspect_rad) + 1.0) / 2.0

        # Save using the working_ds spatial metadata
        save_geotiff(dem_norm_out, slope_norm, working_ds, nodata_value=nodata_value)
        save_geotiff(dem_northness, northness, working_ds, nodata_value=nodata_value)
        save_geotiff(dem_eastness, eastness, working_ds, nodata_value=nodata_value)
            
    return


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
        return None, None
    try:
        left, bottom, right, top = rasterio.transform.array_bounds(src_height, src_width, src_transform)
        dst_transform, dst_width, dst_height = calculate_default_transform(
            src_crs, dst_crs, src_width, src_height, left, bottom, right, top
        )
    except Exception:
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
    except Exception:
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
        return None, None
    if not os.path.isfile(raster_path):
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
    except Exception:
        return None, None
    return out_image[0], out_meta

def open_raster(raster_path, nodata=None, read_all_bands=True, masked=True):
    """
    Open a raster and return its array and metadata.

    Parameters
    ----------
    raster_path : str
        Path to the raster file.
    nodata : float or int, optional
        Nodata value to use. If None, uses the raster's original nodata (if present),
        otherwise falls back to a dtype-based default for masking only.
        If provided, it will also update the returned metadata's 'nodata' field.
    read_all_bands : bool, default True
        If True, returns all bands with shape (count, height, width).
        If False, returns only the first band with shape (height, width).
    masked : bool, default True
        If True, returns a numpy.ma.MaskedArray where nodata values are masked.
        If False, returns a regular numpy array.

    Returns
    -------
    tuple
        (array, metadata) or (None, None) if opening fails.

    Notes
    -----
    - The metadata dict includes keys commonly used by rasterio:
      'driver', 'dtype', 'nodata', 'width', 'height', 'count', 'crs', 'transform'.
    - When `masked=True`, masking uses:
        - `nodata` (if provided), else
        - `src.nodata` (from the file), else
        - a dtype-based default for masking only
      This masking choice does NOT alter pixel values; it only builds a mask.
    """

    def default_nodata(dtype):
        """Fallback nodata for masking when none is defined on the raster."""
        # Pick conservative defaults; adjust to your conventions if needed.
        if np.issubdtype(dtype, np.integer):
            return -9999
        elif np.issubdtype(dtype, np.floating):
            return np.nan
        else:
            return None

    try:
        with rasterio.open(raster_path) as src:
            # Base metadata from source
            out_meta = src.meta.copy()

            # Determine effective nodata to use for masking
            src_dtype = np.dtype(src.dtypes[0])
            original_nodata = src.nodata
            nodata_effective = (
                nodata if nodata is not None
                else (original_nodata if original_nodata is not None
                      else default_nodata(src_dtype))
            )

            # Read array (all bands), then slice if needed
            arr = src.read()  # shape: (count, height, width)
            if not read_all_bands:
                arr = arr[0]  # shape: (height, width)

            # Build a mask if requested
            if masked:
                # Masking depends on whether nodata_effective is NaN or a value
                if isinstance(nodata_effective, float) and np.isnan(nodata_effective):
                    mask = np.isnan(arr)
                elif nodata_effective is not None:
                    mask = (arr == nodata_effective)
                else:
                    mask = np.zeros_like(arr, dtype=bool)

                arr = np.ma.array(arr, mask=mask)

            # Update metadata to reflect what we are returning
            # (height/width/count might be unchanged, but we set explicitly)
            if read_all_bands:
                height, width = arr.shape[-2], arr.shape[-1]
                count = arr.shape[0]
            else:
                height, width = arr.shape[-2], arr.shape[-1]
                count = 1

            out_meta.update({
                "height": height,
                "width": width,
                "count": count,
                # If user specified nodata, reflect that preference in the metadata;
                # otherwise keep the source nodata as-is.
                "nodata": nodata if nodata is not None else original_nodata
            })

            return arr, out_meta

    except Exception:
        return None, None

# -----------------------------
# 6. Save raster
# -----------------------------
def save_raster(array, meta, output_path, dtype=None, cog=False, nodata_out=None):
    if array is None or meta is None:
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
    with rasterio.open(output_path, "w", **out_meta) as dst:
        dst.write(arr, 1)



# Function that builds a stack, writes multiband, and (optionally) saves per-band using save_raster ---
def _ensure_2d_yx(da: xr.DataArray, name=None) -> xr.DataArray:
    """
    Normalize a DataArray to 2D ('y','x'):
    - squeeze a single-band dim if present,
    - reorder dims to ('y','x'),
    - validate it has y/x coords.
    """
    if "band" in da.dims and da.sizes.get("band", 0) == 1:
        da = da.squeeze("band", drop=True)

    if set(da.dims) == {"x", "y"} and tuple(da.dims) != ("y", "x"):
        da = da.transpose("y", "x")

    if da.dims != ("y", "x"):
        raise ValueError(f"Expected 2D DataArray with dims ('y','x'), got dims {da.dims}")

    if "y" not in da.coords or "x" not in da.coords:
        raise ValueError("DataArray must have 'y' and 'x' coordinates for stacking.")

    if name is not None:
        da.name = name
    return da


def build_and_save_stack_from_list(
    arrays,
    output_path="nbs_hotspots.tif",
    band_names=None,
    nodata=np.nan,
    compress="DEFLATE",
    tiled=True,
    windowed=True,
    save_each_band=False,
    per_band_dir=None,
    per_band_dtype=None,
    per_band_cog=False,
    strict_check=True,
    cast_to_float_if_nan=True,
    set_band_descriptions_fallback=True,
):
    """
    Create a multiband stack from a list of rioxarray/xarray DataArrays, save a multiband GeoTIFF,
    and optionally save each band separately using `save_raster`.
    """
    # --- Validate inputs ---
    if arrays is None or len(arrays) == 0:
        raise ValueError("`arrays` must be a non-empty list of xr.DataArray objects.")

    normalized = []
    for i, da in enumerate(arrays):
        if not isinstance(da, xr.DataArray):
            raise TypeError(f"Item {i} in `arrays` is not an xarray.DataArray (got {type(da)}).")
        if not hasattr(da, "rio"):
            raise TypeError(f"Item {i} does not have a .rio accessor. Ensure rioxarray is installed/enabled.")
        normalized.append(_ensure_2d_yx(da, name=getattr(da, "name", f"band_{i+1}")))

    arrays = normalized
    n_bands = len(arrays)

    # Default band names if not provided
    if band_names is None:
        band_names = [da.name if da.name else f"band_{i+1}" for i, da in enumerate(arrays)]
    else:
        if len(band_names) != n_bands:
            raise ValueError("`band_names` length must match number of arrays.")

    # --- Optional strict checks for alignment ---
    if strict_check:
        ref = arrays[0]
        ref_shape = ref.shape
        ref_crs = ref.rio.crs
        ref_transform = ref.rio.transform()
        ref_x = ref.coords["x"].values
        ref_y = ref.coords["y"].values

        for i, da in enumerate(arrays[1:], start=2):
            if da.shape != ref_shape:
                raise ValueError(f"Array {i} has differing shape {da.shape} vs {ref_shape}. Reproject/align first.")
            if da.rio.crs != ref_crs:
                raise ValueError(f"Array {i} has differing CRS {da.rio.crs} vs {ref_crs}. Reproject/align first.")
            if not np.allclose(np.asarray(ref_transform), np.asarray(da.rio.transform()), rtol=0, atol=1e-9):
                raise ValueError("Transforms differ; reproject/align with rio.reproject_match().")
            if not (np.array_equal(ref_x, da.coords["x"].values) and np.array_equal(ref_y, da.coords["y"].values)):
                raise ValueError("x/y coordinates differ; reproject/align before stacking.")

    # --- Prevent nodata/dtype conflicts ---
    if cast_to_float_if_nan and (isinstance(nodata, float) and np.isnan(nodata)):
        if any(np.issubdtype(da.dtype, np.integer) for da in arrays):
            arrays = [da.astype(np.float32) for da in arrays]

    # --- Build the stack (exact join avoids silent coord expansion) ---
    stack = xr.concat(arrays, dim="band", join="exact")
    stack = stack.assign_coords(band=list(range(1, n_bands + 1)))
    stack.rio.write_nodata(nodata, inplace=True)

    # Try band descriptions via rioxarray (may not be available in some versions)
    try:
        stack.rio.write_band_descriptions(list(band_names), inplace=True)
    except Exception:
        pass

    # --- Save multiband raster ---
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    stack.rio.to_raster(
        output_path,
        compress=compress,
        tiled=tiled,
        windowed=windowed
    )

    # --- Fallback: set band descriptions with rasterio if needed ---
    if set_band_descriptions_fallback and band_names:
        try:
            with rasterio.open(output_path, "r+") as dst:
                for idx, desc in enumerate(band_names, start=1):
                    dst.set_band_description(idx, str(desc))
        except Exception:
            pass

    # --- Optionally save per-band rasters using save_raster ---
    if save_each_band:
        # Derive meta directly from the stack (do not use stack.rio.profile)
        height = stack.sizes["y"]
        width = stack.sizes["x"]
        transform = stack.rio.transform()
        crs = stack.rio.crs

        if per_band_dir is None:
            root, _ = os.path.splitext(output_path)
            per_band_dir = f"{root}_bands"
        os.makedirs(per_band_dir, exist_ok=True)

        for b_idx in range(n_bands):
            band_arr = stack.isel(band=b_idx).values
            single_meta = {
                "width": width,
                "height": height,
                "transform": transform,
                "crs": crs,
                "nodata": nodata,
            }
            band_name = band_names[b_idx]
            band_out = os.path.join(per_band_dir, f"{band_name}.tif")

            # Use your existing save_raster
            save_raster(
                array=band_arr,
                meta=single_meta,
                output_path=band_out,
                dtype=per_band_dtype,
                cog=per_band_cog,
                nodata_out=nodata
            )

    return stack

def lare_raster(gdf,crs=4258,layer='dem',sessionid=None):
    """clips layer based on the name with the specified crs based on the passed dataframe 

    Args:
        gdf (Geodataframe): Geopandas dataframe with information an spatial selection (i.e. polygon ar any arbitrary closed surface)
        crs (int, optional): Coordinate reference system, EPSG int representation. Defaults to 4258.
        layer (str, optional): Layer of choice, this layer can be available in the config, otherwise should be a layer that can be found.

    Returns:
        String: name of the raster clipped from the data service
    """
    cfg = get_config()
    tmpdir = cfg.tmpdir
    base = cfg.ows_base

    layer, fname = cfg.resolve_layer(layer)
    outfname = os.path.join(tmpdir, sessionid, fname)

    gdf = gdf.to_crs(crs)
    xmin, ymin, xmax, ymax = gdf.total_bounds

    try:
        cut_wcs(float(xmin), float(ymin), float(xmax), float(ymax), layer, base, outfname, crs=crs, all_box=True)
    except Exception as e:
        logging.error(f'lare_raster: clip of {layer} failed: {e}')
        return None
    return outfname


# -----------------------------
# 4. Fast reclassification using lookup array
# -----------------------------
def reclassify_fast(array, reclass_dict, dtype='int32', nodata_out=None, original_nodata=None):
    if array is None or reclass_dict is None:
        return None
    np_dtype = np.dtype(dtype)
    if nodata_out is None:
        nodata_out = default_nodata(np_dtype)
    
    try:
        reclass_dict = coerce_reclass_dict_to_array_dtype(array, reclass_dict)
    except Exception as e:
        logging.warning('reclassify_fast: coerce failed: %s', e)

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


def aggregate_raster_to_hexagons(raster_path, hexagons, stat='mean', value_range=None, classes=None,
                                   output_column='aggregated_value'):
    """Raster-based zonal stats using vectorized numpy operations.

    Rasterizes *hexagons* onto the source raster grid, then computes
    per-zone statistics without looping over individual zones.

    Parameters
    ----------
    raster_path : str
        Path to a single-band raster file.
    hexagons : GeoDataFrame
        Hexagon polygons; ``output_column`` is added or overwritten in place.
    stat : ``'mean'`` | ``'majority'``
        Aggregation statistic.
    value_range : tuple[float, float] | None
        ``(min, max)`` – only pixels inside this range are considered.
    classes : list[int] | None
        Pixel values to keep (required when *stat* = ``'majority'``).
    output_column : str
        Name of the result column written to *hexagons*.  Defaults to
        ``'aggregated_value'``.  If the column already exists it is dropped
        before writing so that re-runs never produce duplicate column names.

    Returns
    -------
    GeoDataFrame
        *hexagons* with *output_column* populated.
    """
    log_memory_status(f"Start of aggregate_raster_to_hexagons for {os.path.basename(raster_path)}")
    with rasterio.open(raster_path) as src:
        if src.crs is None:
            raise ValueError(f"Raster {raster_path} has no CRS.")

        hex_in_raster_crs = hexagons.to_crs(src.crs) if hexagons.crs != src.crs else hexagons
        n_zones = len(hex_in_raster_crs)
        zone_ids = np.arange(1, n_zones + 1, dtype=np.int32)

        shapes = [
            (geom, int(zone_id))
            for zone_id, geom in zip(zone_ids, hex_in_raster_crs.geometry)
            if geom is not None and not geom.is_empty
        ]
        if not shapes:
            if output_column in hexagons.columns:
                hexagons = hexagons.drop(columns=[output_column])
            hexagons[output_column] = np.nan
            return hexagons

        log_memory_status(f"Before rasterize for {os.path.basename(raster_path)}")
        zone_raster = rasterize(
            shapes=shapes,
            out_shape=(src.height, src.width),
            transform=src.transform,
            fill=0,
            dtype='int32',
            all_touched=False,
        )
        raster_values = src.read(1)
        log_memory_status(f"After reading raster for {os.path.basename(raster_path)}")

        valid_mask = zone_raster > 0
        nodata = src.nodata
        if nodata is not None:
            if np.issubdtype(raster_values.dtype, np.floating) and np.isnan(nodata):
                valid_mask &= ~np.isnan(raster_values)
            else:
                valid_mask &= raster_values != nodata

        if value_range is not None:
            vmin, vmax = value_range
            valid_mask &= (raster_values >= vmin) & (raster_values <= vmax)

        if classes is not None:
            valid_mask &= np.isin(raster_values, np.asarray(classes))

        if not np.any(valid_mask):
            if output_column in hexagons.columns:
                hexagons = hexagons.drop(columns=[output_column])
            hexagons[output_column] = np.nan
            log_memory_status(f"End of aggregate_raster_to_hexagons for {os.path.basename(raster_path)} (no valid data)")
            return hexagons

        zones = zone_raster[valid_mask]
        vals = raster_values[valid_mask]

        result = np.full(n_zones, np.nan, dtype='float64')
        if stat == 'mean':
            vals_f = vals.astype('float64', copy=False)
            sums = np.bincount(zones, weights=vals_f, minlength=n_zones + 1)
            counts = np.bincount(zones, minlength=n_zones + 1)
            means = np.full(n_zones + 1, np.nan, dtype='float64')
            nonzero = counts > 0
            means[nonzero] = sums[nonzero] / counts[nonzero]
            result = means[1:]
        elif stat == 'majority':
            if classes is None or len(classes) == 0:
                raise ValueError("'majority' statistic requires non-empty 'classes'.")

            classes_arr = np.sort(np.asarray(classes, dtype='int32'))
            vals_i = vals.astype('int32', copy=False)
            class_pos = np.searchsorted(classes_arr, vals_i)
            in_bounds = (class_pos >= 0) & (class_pos < len(classes_arr))
            exact = np.zeros_like(in_bounds, dtype=bool)
            exact[in_bounds] = classes_arr[class_pos[in_bounds]] == vals_i[in_bounds]

            zones = zones[exact]
            class_pos = class_pos[exact]
            if zones.size > 0:
                counts = np.zeros((n_zones + 1, len(classes_arr)), dtype=np.int32)
                np.add.at(counts, (zones, class_pos), 1)
                zone_totals = counts[1:].sum(axis=1)
                has_vals = zone_totals > 0
                mode_pos = np.argmax(counts[1:], axis=1)
                result[has_vals] = classes_arr[mode_pos[has_vals]]
        else:
            raise ValueError(f"Unsupported statistic '{stat}'.")

        if output_column in hexagons.columns:
            hexagons = hexagons.drop(columns=[output_column])
        hexagons[output_column] = result
        log_memory_status(f"End of aggregate_raster_to_hexagons for {os.path.basename(raster_path)}")
        return hexagons


def aggregate_coastal(sessionid):
    cfg = get_config()

    cwd = os.path.join(cfg.tmpdir, sessionid)
    logging.info('aggregate_coastal: session=%s', sessionid)

    hf = os.path.join(cwd, f'hexagons_coastal_{sessionid}.gpkg')
    hexagons = gpd.read_file(hf)

    with rasterio.Env():
        try:
            clctif = os.path.join(cwd, 'clc.tif')
            hexagons = aggregate_raster_to_hexagons(
                clctif, hexagons, stat='majority', classes=[1, 2, 3, 4, 5, 6],
                output_column='landcover_aggregated',
            )
        except Exception as e:
            logging.error('aggregate_coastal: landcover aggregation failed: %s', e, exc_info=True)

        try:
            demtif = os.path.join(cwd, 'dem.tif')
            hexagons = aggregate_raster_to_hexagons(
                demtif, hexagons, stat='mean', value_range=(0, 200),
                output_column='dem_aggregated',
            )
        except Exception as e:
            logging.error('aggregate_coastal: DEM aggregation failed: %s', e, exc_info=True)

        try:
            imperviousness_tif = os.path.join(cwd, 'imperviousness.tif')
            hexagons = aggregate_raster_to_hexagons(
                imperviousness_tif, hexagons, stat='mean', value_range=(30, 100),
                output_column='imperviousness_aggregated',
            )
        except Exception as e:
            logging.error('aggregate_coastal: imperviousness aggregation failed: %s', e, exc_info=True)

    try:
        hexagons.to_file(os.path.join(cwd, f'hexagons_coastal_{sessionid}.gpkg'), driver='GPKG')
    except Exception as e:
        logging.error('aggregate_coastal: save failed: %s', e)      
    
    
    
def aggregate_hazard(sessionid, hazardtif, archetype):
    cfg = get_config()

    cwd = os.path.join(cfg.tmpdir, sessionid)
    logging.info('aggregate_hazard: session=%s archetype=%s', sessionid, archetype)

    hf = os.path.join(cwd, f'hexagons_{archetype}_{sessionid}.gpkg')
    hexagons = gpd.read_file(hf)

    with rasterio.Env():
        try:
            hexagons = aggregate_raster_to_hexagons(
                hazardtif, hexagons, stat='mean',
                output_column='hazard_aggregated',
            )
        except Exception as e:
            logging.error('aggregate_hazard: raster aggregation failed: %s', e, exc_info=True)

    try:
        hexagons.to_file(os.path.join(cwd, f'hexagons_{archetype}_{sessionid}.gpkg'), driver='GPKG')
    except Exception as e:
        logging.error('aggregate_hazard: save failed: %s', e)   