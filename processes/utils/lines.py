# Copyright (C) 2018 Deltares
# SPDX-License-Identifier: GPL-3.0-or-later

import math
#from osgeo import ogr
from typing import Tuple
from shapely.geometry import LineString
from shapely.ops import substring


def _distance(a, b):

    """ Return the distance separating points a and b.

    a and b should each be an (x, y) tuple.

    Warning: This function uses the flat surface formulae, so the output may be
    inaccurate for unprojected coordinates, especially over large distances.

    """

    dx = abs(b[0] - a[0])
    dy = abs(b[1] - a[1])
    return (dx ** 2 + dy ** 2) ** 0.5

def _get_split_point(a, b, dist):

    """ Returns the point that is <<dist>> length along the line a b.

    a and b should each be an (x, y) tuple.
    dist should be an integer or float, not longer than the line a b.

    """

    dx = b[0] - a[0]
    dy = b[1] - a[1]

    m = dy / dx
    c = a[1] - (m * a[0])

    x = a[0] + (dist**2 / (1 + m**2))**0.5
    y = m * x + c
    # formula has two solutions, so check the value to be returned is
    # on the line a b.
    if not (a[0] <= x <= b[0]) and (a[1] <= y <= b[1]):
        x = a[0] - (dist**2 / (1 + m**2))**0.5
        y = m * x + c

    return x, y


def split_line_single(line: LineString, length: float) -> Tuple[LineString, LineString]:
    """
    Split a Shapely LineString into two parts at a given distance from the start.

    Parameters
    ----------
    line : shapely.geometry.LineString
        Input line geometry (2D; 3D is accepted but length is computed in 2D).
    length : float
        Distance from the line's start point at which to split. Units must match the CRS.

    Returns
    -------
    first_part : LineString
        The first 'length' units of the line (or the whole line if length >= line.length).
    remainder : LineString
        The rest of the line (empty if length >= line.length).
    """
    if not isinstance(line, LineString):
        raise TypeError("Expected a shapely LineString.")

    if length <= 0:
        # Nothing taken from the start
        return LineString([]), line

    L = line.length
    if length >= L:
        # Entire line is the first part
        return line, LineString([])

    # substring distances are absolute along the line when normalized=False
    first = substring(line, 0.0, length, normalized=False)
    rest  = substring(line, length, L, normalized=False)

    # Ensure both are LineStrings (substring returns LineString for valid ranges)
    if first.is_empty:
        first = LineString([])
    if rest.is_empty:
        rest = LineString([])

    return first, rest

def split_line_multiple(line, length=None, n_pieces=None):

    """ Splits a ogr wkbLineString into multiple sub-strings, either of
    a specified <<length>> or a specified <<n_pieces>>.

    line should be an ogr LineString Geometry
    Length should be a float or int.
    n_pieces should be an int.
    Either length or n_pieces should be specified.

    Returns a list of ogr wkbLineString Geometries.

    """

    if not n_pieces:
        n_pieces = int(math.ceil(line.Length() / length))
    if not length:
        length = line.Length() / float(n_pieces)

    line_segments = []
    remainder = line

    for i in range(n_pieces - 1):
        segment, remainder = split_line_single(remainder, length)
        line_segments.append(segment)
    else:
        line_segments.append(remainder)

    return line_segments


# def split_line_single(line, length):

#     """ Returns two ogr line geometries, one which is the first length
#     <<length>> of <<line>>, and one one which is the remainder.

#     line should be a ogr LineString Geometry.
#     length should be an integer or float.

#     """

#     line_points = line.GetPoints()
#     sub_line = ogr.Geometry(ogr.wkbLineString)

#     while length > 0:
#         d = _distance(line_points[0], line_points[1])
#         if d > length:
#             split_point = _get_split_point(line_points[0], line_points[1], length)
#             sub_line.AddPoint(line_points[0][0], line_points[0][1])
#             sub_line.AddPoint(*split_point)
#             line_points[0] = split_point
#             break

#         if d == length:
#             sub_line.AddPoint(*line_points[0])
#             sub_line.AddPoint(*line_points[1])
#             line_points.remove(line_points[0])
#             break

#         if d < length:
#             sub_line.AddPoint(*line_points[0])
#             line_points.remove(line_points[0])
#             length -= d

#     remainder = ogr.Geometry(ogr.wkbLineString)
#     for point in line_points:
#         remainder.AddPoint(*point)

#     return sub_line, remainder

