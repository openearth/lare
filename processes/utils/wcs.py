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
import numpy as np
from owslib.wcs import WebCoverageService
from owslib.util import Authentication
from shapely import wkt
import rasterio
from rasterio.io import MemoryFile
from rasterio.shutil import copy as rio_copy


import logging

logger = logging.getLogger(__name__)

# TODO Check how can it be improved
## TO READ WCS outputs

class WCS:
    """WCS object to get metadata etc and to get grid."""

    def __init__(self, host, layer, username=None, password=None):
        self.username = username
        self.password = password
        self.id = layer
        self.wcs = (
            WebCoverageService(
                host,
                version="1.0.0",
                auth=Authentication(username=self.username, password=self.password),
            )
            if self.password and self.username
            else WebCoverageService(host, version="1.0.0")
        )
        self.layer = self.wcs[self.id]
        self.cx, self.cy = map(int, self.layer.grid.highlimits)
        self.crs = self.layer.boundingboxes[0]["nativeSrs"]
        self.bbox = self.layer.boundingboxes[0]["bbox"]
        self.lx, self.ly, self.hx, self.hy = map(float, self.bbox)
        self.resx, self.resy = (self.hx - self.lx) / self.cx, (
            self.hy - self.ly
        ) / self.cy
        self.width = self.cx
        self.height = self.cy


    def getw(self, fn: str) -> str:
        """
        Downloads raster via WCS and writes a Cloud-Optimized GeoTIFF (COG) to `fn`.
        Falls back to a plain GeoTIFF if COG creation fails. Returns `fn`.
        Requires GDAL >= 3.1 with COG driver (you have 3.12.1).
        """
        # 1) Request the coverage (bytes/stream from WCS)
        gc = self.wcs.getCoverage(
            identifier=self.id,
            bbox=self.bbox,
            format="GeoTIFF",
            crs=self.crs,
            width=self.width,
            height=self.height,
        )

        try:
            # 2) Read the response as bytes once (for both main path and fallback)
            data = gc.read() if hasattr(gc, "read") else gc
            if not isinstance(data, (bytes, bytearray)):
                # some WCS libs return file-like; ensure bytes
                data = data.read()

            # 3) Open the in-memory GeoTIFF with Rasterio
            with MemoryFile(data) as mem:
                with mem.open() as src:
                    # Choose a good predictor based on data type:
                    #   - 2 for integer data
                    #   - 3 for floating-point (often better compression)
                    first_dtype = src.dtypes[0]
                    predictor = 3 if first_dtype.startswith("float") else 2

                    # 4) Let GDAL's COG driver build overviews + layout properly
                    #    (no intermediate temp file needed)
                    rio_copy(
                        src,
                        fn,
                        driver="COG",
                        BLOCKSIZE=512,            # internal tiling (multiple of 16)
                        COMPRESS="DEFLATE",       # lossless, widely used for COG
                        PREDICTOR=predictor,      # 2=int; 3=float
                        NUM_THREADS="ALL_CPUS",
                        BIGTIFF="IF_SAFER",
                        RESAMPLING="NEAREST",     # overview resampling; adjust if needed
                        # LEVELS="AUTO",          # optional: let GDAL decide overview levels
                        # COPY_SRC_OVERVIEWS="YES"  # only if you pre-built overviews
                    )

            logging.info(f"✔️ Successfully created COG: {fn}")

        except Exception as e:
            # 5) Fallback: write the raw response as a plain GeoTIFF
            try:
                with open(fn, "wb") as f:
                    f.write(data)
                logging.warning(f"⚠️ COG creation failed ({e}); wrote plain GeoTIFF to {fn}")
            except Exception as e2:
                logging.error(f"❌ Failed to write fallback GeoTIFF: {e2}")
                raise
        return fn


    def getw_with_auth(self, fn):
        """Downloads raster and returns filename of written GEOTIFF in the tmp dir."""
        gc = self.wcs.getCoverage(
            identifier=self.id,
            bbox=self.bbox,
            format="GeoTIFF",
            crs=self.crs,
            width=self.width,
            height=self.height,
            auth=Authentication(username=self.username, password=self.password),
        )
        f = open(fn, "wb")
        f.write(gc.read())
        f.close()
        return fn



## TO handle transects
class LS:
    """Intersection on grid line"""

    def __init__(self, awkt, crs, host, layer, username=None, password=None, sampling=1):
        self.wwkt = awkt
        self.crs = crs
        self.gs = WCS(
            host, layer , username, password
        )  # Initiates WCS service to get some parameters about the grid.
        self.sampling = sampling

    def line(self):
        """Creates WCS parameters and sample coordinates for cells in raster based on line input."""
        self.ls = wkt.loads(self.wwkt)
        self.ax, self.ay, self.bx, self.by = self.ls.bounds
        # TODO http://stackoverflow.com/questions/13439357/extract-point-from-raster-in-gdal

        """if first x is larger than second, coordinates will be flipped during process of defining bounding box !!!!
           next lines introduce a boolean flip variable used in the last part of this process"""
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
        if self.gs.username and self.gs.password:
             self.gs.getw_with_auth(fname)
        else:
            self.gs.getw(fname)
        return
