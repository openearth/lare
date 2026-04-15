# -*- coding: utf-8 -*-
# Copyright notice
#   --------------------------------------------------------------------
#   Copyright (C) 2025 Deltares
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

# imports
import numpy as np
import rasterio
from rasterio.enums import Resampling
import geopandas
import logging

# local
from processes.config import get_config
from processes.utils import tempfile, load_reclass_topo, load_reclass_table, compute_nodata_cast
from processes.utils.wfs import clipfromwfs_cql
from processes.utils.vector import ensure_metric
from processes.utils.raster import cut_wcs, compute_slope_aspect_from_dem, reclassify_fast, lare_raster
from processes.reclass_topo import classify_elevation_raster, create_hazard_rasters
from processes.utils.geoserver import filtervectorbyvector, load2geoserver, publish_gpkg, createvieweroutput

logger = logging.getLogger(__name__)


"""
stepwise approach:
1. retrieve geodataframe from WFS
2.a derive DEM from WCS
2.b create slope, aspect, elevation hazards from the scores
4.a derive CLC from WCS
4.b create varous hazard mitigation rasters from CLC and scores
"""

def handler_eunis(gdf,hazard=None):
    # clip EUNIS raster from OGC service
    outeunis = lare_raster(gdf, 3035, 'eunis')

def classifyraster(hazard, clc_array, src_nodata, outclc, meta):
        cfg = get_config()
        clc_lut = os.path.normpath(os.path.join(os.path.dirname( __file__ ), '..', cfg.hazard_clc_scores[hazard]))

        #load_reclass_table 
        class_dct = load_reclass_table(clc_lut,'clc','score')
        if class_dct is None:
            logging.error(f'!-- classification directionary not found {clc_lut}')
            return None

        # find out what the type is of the value in the csv
        first_key = next(iter(class_dct))
        value = class_dct[first_key]
        dt = np.array(value).dtype #target dtype for this hazard (numpy dtype)

        nodata_cast = compute_nodata_cast(src_nodata, dt)

        # classify the arry witht he dictionary and the opened clc array
        clc_archetype_arr = reclassify_fast(clc_array,class_dct,dtype=str(dt))

        # define output and save raster
        clc_hazard = outclc.replace('clc',f'clc_{hazard}')

        # enable writing to COG (reduces storage and improves speed)
        meta.update(
            dtype=dt,
            nodata=nodata_cast,
            tiled=False,                     # COG requirement
            blockxsize=512,                 # typical COG block size
            blockysize=512,
            compress='LZW',             # common for COGs
            # predictor=2,                    # improves compression for int/float
            BIGTIFF='IF_NEEDED'
        )

        # Write main image
        with rasterio.open(clc_hazard, 'w', **meta) as dst:
            dst.write(clc_archetype_arr, 1)

            # Build overviews (COG requirement)
            oviews = [2, 4, 8, 16, 32]
            dst.build_overviews(oviews, Resampling.nearest)

            # Make sure metadata reflects overviews
            dst.update_tags(ns='rio_overview', resampling='nearest')
        return clc_hazard

def handler_coastline(sessionid):
    # find the region from the sessionid, this should be stored in the sessionid
    # retrieve the geodataframe for the region
    # clip the coastline from WFS and create a raster from the coastline inland with a certain distance (e.g. 1km, 5km, 10km)
    # return the wms layer to the front end
    sessionid = 321546
    # find region.gpgk from sessionid
    cfg = get_config()
    geoserver_url = cfg.ows_base
    tmpdir = cfg.tmpdir
    sessiondir = os.path.join(tmpdir, str(sessionid))
    gdfpath = os.path.join(sessiondir, 'region.gpkg')
    if not os.path.exists(gdfpath):
        logging.error(f'!-- Coastline handler: unable to find geodataframe for sessionid {sessionid} at path {gdfpath}')
        return None

    # buffer the gdf with a distance of 100 m
    gdf = geopandas.read_file(gdfpath)
    # check crs, this should be a metric system (default to 3035)
    gdf = ensure_metric(gdf, 3035)

    bufgdf = gdf.copy()
    bufgdf["geometry"] = gdf.buffer(100)
    bufgdf.set_geometry("geometry", inplace=True)
    bufgdf.to_file(os.path.join(sessiondir, 'buffer.gpkg'), driver='GPKG')  
    coastlinegdf = filtervectorbyvector(geoserver_url, bufgdf, 3035, 'coastline', 3035)
    coastlinegdf.to_file(os.path.join(sessiondir, 'coastline.gpkg'), driver='GPKG')
    

def handler_clc(gdf,hazard=None):
    """Based on the geodataframe and the specified hazard at least 2 rasters will be created. 
       1. clip of CLC from WCS
       2. either 1 (if specified) either several (if hazard = None) will be created 
    
    Args:
        gdf (geodatafram): geodatafram of clipped WFS (for now nuts region, but can be any GDF)
        hazard (string, optional): Hazard specified, this needs to be in the app.yml (scores hazards section in list). 
                                   Defaults to None. In that case the application will loop over all hazards

    Returns:
        wmslay (list): returns a list of wmslayers
    """
    wmslay = None

    # clip Corine Landcover layer from OGC service
    outclc = lare_raster(gdf, 3035, 'clc')

    # load raster into array
    with rasterio.open(outclc) as src:
        clc_array = src.read(1)
        meta = src.meta
        src_nodata = src.nodata

    # derive hazards using csv from
    cfg = get_config()
    hazards = cfg.hazard_clc_scores
    # add the hazards to a list
    lsthazards = []
    if hazard is None:
        for hazard in hazards.keys():
            clc_hazard = classifyraster(hazard, clc_array, src_nodata, outclc, meta)
            lsthazards.append(clc_hazard)
    else:
        clc_hazard = classifyraster(hazard, clc_array, src_nodata, outclc, meta)
        lsthazards.append(clc_hazard)
    
    wmslay = load2geoserver(lsthazards)
    return wmslay

def handler_dem(gdf):
    msg = None
    # step 2a, clip dem using extent of Geodataframe
    # not very nice, but ... derive tmp path from outdem
    outdem = lare_raster(gdf, 4258, 'dem')
    outslope = outdem.replace('dem','slope')
    outaspect = outdem.replace('dem','aspect')
    outnorm = outdem.replace('dem','dem_norm')
    outeast = outdem.replace('dem','dem_eastness')
    outnorth = outdem.replace('dem','dem_northness')
    
    # step 2b create slope, aspect, eastness, northness from the dem
    compute_slope_aspect_from_dem(
        dem_path=outdem,
        slope_out=outslope,
        aspect_out=outaspect,
        dem_norm_out = outnorm,
        dem_eastness = outeast,
        dem_northness = outnorth,
        slope_unit="degree",           # or "percent"
        auto_reproject_to_utm=False,    # set False if CRS is already metric (e.g., UTM)
        nodata_value=-9999.0)
    
    # step 2c is deriving hazards from dem
    cfg = get_config()
    
    # get url and layer
    output_path = os.path.normpath(os.path.join(os.path.dirname( __file__ ), '..', cfg.tmp_base))
    output_path = r'c:\develop\lare\processes\tmp'
    csv_scores = cfg.topo_hazards_csv

    # create a raster based on DEM where DEM is classified in lowland, midland and upland
    # use topo_elevationscores.csv to create this intermediate dataset
    classification_df = load_reclass_topo(csv_scores)

    # call function that classifies DEM into a zonal raster defining lowland, midland and highland    
    zone_dem = classify_elevation_raster(outdem, classification_df)

    # call function that creates susceptibility layers for various hazards.
    create_hazard_rasters(outdem, classification_df)
    msg = 'hazards based on dem created'
    return msg

def mainhandler(name):
    """Based on the given name (nuts name) of a region, a clip will be created from a WFS and via WCS clips 
    of CLC, EUNIS and DEM will be created and derived susceptibility maps will be created using the lookuptables.

    Args:
        name (string): nutsname (bear in mind level 3 are small and fast...)

    Returns:
        derived maps: For now nothing is done with these maps
    """
    name = name.split(':')[1].replace('}','')

    try:
        gdf = clipfromwfs_cql(name)
    except Exception as e:
        logging.error('mainhandler: WFS clip failed for %s: %s', name, e)
        return None

    handler_clc(gdf)
    handler_eunis(gdf)

    # TODO: provide front end with correct, not sure yet what is needed.

def mainhandler_hazard(name, hazard):
    """
    Creates derived data based on filter dataframe of nuts from WFS, clip from raster CLC via WCS and 
    provides wms to front end from derived maps from lookuptables
    
    args:
        name (string): name of nuts region
        hazard (string): name of hazard (should be in the list of hazards with associated lookuptables)
    """    
    msg = None

    cfg = get_config()
    jsonhazard = cfg.hazard_titles
    wmsurl = cfg.geoserver.url

    if hazard not in jsonhazard:
        raise ValueError(f'Hazard {hazard!r} not in defined hazards')

    gdf = clipfromwfs_cql(name)
    if gdf is None or gdf.empty:
        raise ValueError(f'No features found for region {name!r}')

    wmslay = handler_clc(gdf, hazard=hazard)
    return createvieweroutput(wmslay, 'Mitigation score', jsonhazard, wmsurl)