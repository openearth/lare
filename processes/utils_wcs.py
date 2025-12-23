# -*- coding: utf-8 -*-
# Copyright notice
#   --------------------------------------------------------------------
#   Copyright (C) 2016 Deltares
#       Joan Sala
#
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

# local imports
import os
import json
from typing import Tuple
import requests

#import os
#import string
#import math
import logging
#import tempfile
#import simplejson as json
import numpy as np
#from pyproj import Proj, transform
from shapely import wkt
from owslib.wcs import WebCoverageService
#from osgeo import gdal
#from random import choice
#from scipy.ndimage import map_coordinates

import logging

DEFAULT_TIMEOUT = 30

logging.basicConfig(level=logging.INFO)

def get_wcs_geotiff_bytes_kvp(
    wcs_url: str,
    layer_name: str,
    bbox: Tuple[float, float, float, float],
    crs: str = "EPSG:3035",
    version: str = "1.1.0",
    timeout: int = DEFAULT_TIMEOUT,
) -> bytes:
    """
    Perform WCS 2.0.1 GetCoverage via KVP with subset along EPSG:3035 axes (E/N).
    Returns GeoTIFF bytes.
    """
    minx, miny, maxx, maxy = bbox
    minx = float(bbox[0].min())
    miny = float(bbox[2].min())
    maxx = float(bbox[1].min())
    maxy = float(bbox[3].min())
    tplbbox = (minx,miny,maxx,maxy)
    params = [
            ("service", "WCS"),
            ("version", version),
            ("request", "GetCoverage"),
            ("identifier", layer_name),
            ("format", "GeoTIFF"),
            ("crs", f"EPSG:{crs.split(':')[-1]}"),
            ("BoundingBox", f"{tplbbox[0]},{tplbbox[1]},{tplbbox[2]},{tplbbox[3]}"),
            ]
    resp = requests.get(wcs_url, params=params, timeout=timeout)
    print(resp.content)
    resp.raise_for_status()
    return resp.content


def get_wcs_geotiff_bytes(
    wcs_url: str,
    layer_name: str,
    bbox: Tuple[float, float, float, float],
    crs: str = "EPSG:3035",
    timeout: int = DEFAULT_TIMEOUT,
) -> bytes:
    """
    Try KVP-based WCS GetCoverage first; if it fails, fallback to OWSLib's WebCoverageService.
    """
    try:
        return get_wcs_geotiff_bytes_kvp(wcs_url, layer_name, bbox, crs=crs, version="2.0.1", timeout=timeout)
    except Exception:
        # OWSLib fallback
        wcs = WebCoverageService(wcs_url, version="2.0.1", timeout=timeout)
        # GeoServer with EPSG:3035 often uses axes E/N; OWSLib can also accept axis URIs but is finicky
        # We'll still try subset as KVP via owslib's getCoverage
        try:
            resp = wcs.getCoverage(
                identifier=layer_name,
                format="image/geotiff",
                               crs=crs,
                subset=[("E", float(bbox[0].min()), float(bbox[2]).min()), ("N", float(bbox[1].min()), float(bbox[3].min()))])
            return resp.read()
        except Exception:
            # final fallback without subset (full coverage) – beware of large downloads
            resp = wcs.getCoverage(identifier=layer_name, format="image/geotiff")


## TO READ WCS outputs
class WCS:
    """WCS object to get metadata etc and to get grid."""

    def __init__(self, host, layer):
        self.id = layer
        self.wcs = WebCoverageService(host, version="1.0.0")
        logging.info("---Init WCS---".format(self.wcs))
        self.layer = self.wcs[self.id]
        # _, self.format, self.identifier = self.layer.keywords
        self.cx, self.cy = map(int, self.layer.grid.highlimits)
        self.crs = self.layer.boundingboxes[0]["nativeSrs"]
        self.bbox = self.layer.boundingboxes[0]["bbox"]
        self.lx, self.ly, self.hx, self.hy = map(float, self.bbox)
        self.resx, self.resy = (self.hx - self.lx) / self.cx, (
            self.hy - self.ly
        ) / self.cy
        self.width = self.cx
        self.height = self.cy

    def getw(self, fn):
        """Downloads raster and returns filename of written GEOTIFF in the tmp dir."""
        gc = self.wcs.getCoverage(
            identifier=self.id,
            bbox=self.bbox,
            format="GeoTIFF",
            crs=self.crs,
            width=self.width,
            height=self.height,
        )
        logging.info("---GET COVERAGE---{}".format(gc))
        logging.info("--- Fn---{}".format(fn))
        f = open(fn, "wb")
        f.write(gc.read())
        f.close()
        return fn


## TO handle transects
class LS:
    """Intersection on grid line"""

    def __init__(self, awkt, crs, host, layer, sampling=1):
        self.wkt = awkt
        self.crs = crs
        self.gs = WCS(
            host, layer
        )  # Initiates WCS service to get some parameters about the grid.
        self.sampling = sampling

    def line(self):
        """Creates WCS parameters and sample coordinates for cells in raster based on line input."""
        self.ls = wkt.loads(self.wkt)
        self.ax, self.ay, self.bx, self.by = self.ls.bounds
        # TODO http://stackoverflow.com/questions/13439357/extract-point-from-raster-in-gdal

        """if first x is larger than second, coordinates will be flipped during process of defining bounding box !!!!
           next lines introduce a boolean flip variable used in the last part of this proces"""
        flipx = False
        flipy = False
        ax, bx = self.ls.coords.xy[0]
        ay, by = self.ls.coords.xy[1]

        if ax >= bx:
            flipx = True
        if ay >= by:
            flipy = True

        """get raster coordinates"""
        self.ax = (
            self.ax - self.gs.lx
        )  # coordinates minus coordinates of raster, start from 0,0
        self.ay = self.ay - self.gs.ly
        self.bx = self.bx - self.gs.lx
        self.by = self.by - self.gs.ly
        self.x1, self.y1 = int(self.ax // self.gs.resx), int(self.ay // self.gs.resy)
        self.x2, self.y2 = (
            int(self.bx // self.gs.resx) + 1,
            int(self.by // self.gs.resy) + 1,
        )
        self.gs.bbox = (
            self.x1 * self.gs.resx + self.gs.lx,
            self.y1 * self.gs.resy + self.gs.ly,
            self.x2 * self.gs.resx + self.gs.lx,
            self.y2 * self.gs.resy + self.gs.ly,
        )
        self.gs.width = abs(self.x2 - self.x1)  # difference of x cells
        self.gs.height = abs(self.y2 - self.y1)

        """ here we go back to our line again instead of calculating bbox for wcs request."""
        self.ax, self.bx = self.ls.coords.xy[0]
        self.ay, self.by = self.ls.coords.xy[1]

        # coordinates minus coordinates of raster, start from 0,0
        self.ax = self.ax - self.gs.lx
        self.ay = self.ay - self.gs.ly
        self.bx = self.bx - self.gs.lx
        self.by = self.by - self.gs.ly

        if flipx and flipy:  # who draws these lines?
            # top right to bottom left
            self.x2, self.y2 = int(self.bx // self.gs.resx), int(
                self.by // self.gs.resy
            )
            self.x1, self.y1 = (
                int(self.ax // self.gs.resx) + 1,
                int(self.ay // self.gs.resy) + 1,
            )
        elif flipx:
            # bottom right to top left
            self.x2, self.y1 = int(self.bx // self.gs.resx), int(
                self.ay // self.gs.resy
            )
            self.x1, self.y2 = (
                int(self.ax // self.gs.resx) + 1,
                int(self.by // self.gs.resy) + 1,
            )
        elif flipy:
            # top left to bottom right
            self.x1, self.y2 = int(self.ax // self.gs.resx), int(
                self.by // self.gs.resy
            )
            self.x2, self.y1 = (
                int(self.bx // self.gs.resx) + 1,
                int(self.ay // self.gs.resy) + 1,
            )
        else:
            # normal
            self.x1, self.y1 = int(self.ax // self.gs.resx), int(
                self.ay // self.gs.resy
            )
            self.x2, self.y2 = (
                int(self.bx // self.gs.resx) + 1,
                int(self.by // self.gs.resy) + 1,
            )

        # From upperright to lower left x values become negative
        # Subdivide the line into sampling points of the raster.
        # Takes longest dimension and uses number of cells * sampling as the
        # number of subdivisions.
        # Grid of subdivions is pixel grid - 0.5
        self.subdiv = int(max(self.gs.width, self.gs.height)) * self.sampling
        self.xlist = np.linspace(
            (self.ax / self.gs.resx) - min(self.x1, self.x2),
            (self.bx / self.gs.resx) - min(self.x1, self.x2),
            num=self.subdiv,
        )
        self.ylist = np.linspace(
            (self.ay / self.gs.resy) - min(self.y1, self.y2),
            (self.by / self.gs.resy) - min(self.y1, self.y2),
            num=self.subdiv,
        )

    def getraster(self, fname, all_box=False):
        """Returns values of line intersection on downlaoded geotiff from wcs."""
        self.gs.getw(fname)
        return
