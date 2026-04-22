# Copyright (C) 2018 Deltares
# SPDX-License-Identifier: GPL-3.0-or-later

import io
import os
import json
import requests
from functools import lru_cache
from io import BytesIO
import geopandas as gpd
import logging
import re
from owslib.fes import PropertyIsLike, And
from owslib.wfs import WebFeatureService
from owslib.etree import etree as ET

from processes.config import get_config

logger = logging.getLogger(__name__)

_GEOMETRY_FIELD_FALLBACK = 'geom'


@lru_cache(maxsize=128)
def get_geometry_field(owsurl: str, typename: str) -> str:
    """Return the geometry attribute name for a WFS layer, cached per process.

    Uses ``WebFeatureService.get_schema`` (owslib) to query the layer
    schema via DescribeFeatureType.  Falls back to ``'geom'`` when the
    service is unreachable or the schema cannot be parsed.

    Args:
        owsurl: Base OWS/WFS endpoint (e.g. ``http://host/geoserver/ows``).
        typename: Fully-qualified layer name (e.g. ``'socio_economic:hospitals'``).

    Returns:
        The name of the geometry column (e.g. ``'geom'``, ``'the_geom'``,
        ``'geometry'``).
    """
    try:
        wfs = WebFeatureService(url=owsurl, version='2.0.0')
        schema = wfs.get_schema(typename)
        geom_col = schema.get('geometry_column')
        if geom_col:
            logger.debug('get_geometry_field: %s → %s (via get_schema)', typename, geom_col)
            return geom_col
    except Exception as e:
        logger.debug('get_geometry_field: get_schema failed for %s: %s', typename, e)

    # Fallback: parse DescribeFeatureType XML directly.
    try:
        params = {
            'service': 'WFS',
            'version': '2.0.0',
            'request': 'DescribeFeatureType',
            'typeName': typename,
            'outputFormat': 'application/json',
        }
        r = requests.get(owsurl, params=params, timeout=15)
        if r.status_code == 200:
            data = r.json()
            for prop in data.get('featureTypes', [{}])[0].get('properties', []):
                if 'gml' in prop.get('type', '').lower() or prop.get('type', '').lower() in (
                    'point', 'linestring', 'polygon', 'multipolygon', 'multilinestring', 'multipoint',
                    'geometry', 'geometrycollection',
                ):
                    logger.debug('get_geometry_field: %s → %s (via DescribeFeatureType JSON)', typename, prop['name'])
                    return prop['name']
    except Exception as e:
        logger.debug('get_geometry_field: DescribeFeatureType fallback failed for %s: %s', typename, e)

    logger.warning(
        'get_geometry_field: could not resolve geometry field for %s; falling back to %r',
        typename, _GEOMETRY_FIELD_FALLBACK,
    )
    return _GEOMETRY_FIELD_FALLBACK


def _is_numeric_literal(value):
    """Return True when value can be safely used as an unquoted numeric CQL literal."""
    if isinstance(value, (int, float)):
        return True
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    return bool(re.fullmatch(r"-?\d+(\.\d+)?", stripped))


def _to_cql_literal(value):
    """Convert Python value to a safe CQL literal, stripping any existing quotes."""
    # First, strip any existing surrounding quotes (single or double)
    str_value = str(value).strip()
    if (str_value.startswith("'") and str_value.endswith("'")) or \
       (str_value.startswith('"') and str_value.endswith('"')):
        str_value = str_value[1:-1]
    
    # Check if numeric (after quote removal)
    if _is_numeric_literal(str_value):
        return str_value
    
    # Quote and escape for CQL string literal
    safe_value = str_value.replace("'", "''")
    return f"'{safe_value}'"

def wfs_filter(name_contains=None, crs='4326'):
    """
    Returns a GeoDataFrame filtered from WFS using OGC filters.
    """
    cfg = get_config()
    url = cfg.wfs_nuts.url
    typename = cfg.wfs_nuts.layer
    name_field = cfg.wfs_nuts.name_field

    # Instantiate WFS (prefer 2.0.0 if supported)
    try:
        wfs = WebFeatureService(url=url, version="2.0.0")
        logging.info("----!!! wfs_filter: wfs succesfully initialised")
    except Exception as e:
        logging.info("----!!! wfs_filter: wfs not initialised")
        wfs = None
        return None
        
    # Build filters
    filters = []
    if name_contains:
        # Case-insensitive substring match
        filters.append(
            PropertyIsLike(
                propertyname=name_field,
                literal=f"%{name_contains}%",
                wildCard="%",
                singleChar='.',
                escapeChar="!",
                matchCase=False
            )
        )

    ogc_filter = None
    if len(filters) == 1:
        ogc_filter = filters[0]
    elif len(filters) > 1:
        ogc_filter = And(filters)

    # Request GeoJSON; srsName ensures coordinate axis handling
    gdf = None
    # try:
    resp = wfs.getfeature(
        typename=[typename],
        filter=ogc_filter,
        outputFormat="application/json",  # GeoServer supports this
        srsname=f'urn:ogc:def:crs:EPSG::{crs}'
    )
    #geojson = json.loads(resp.read())
    # todo --> apparantly filtering doesn't work....!!!
    agdf = gpd.read_file(BytesIO(resp.content()))
    gdf = agdf[agdf[f"{name_field}"] == f"{name_contains}"]
    logging.info("----!!! wfs_filter: geodataframe from filter for region {}".format(name_contains))
    # except Exception as e:
    #     logging.info("----!!! wfs_filter: wfs filtering not succesful")
    return gdf


def clipfromwfs_cql(filtervalue, url=None, name_field=None, typename=None):
    """Fetch a GeoDataFrame from a WFS using a CQL equality filter.

    All optional parameters fall back to values from the centralised
    ``get_config()`` when not supplied.

    Args:
        filtervalue: Value to match against *name_field* via CQL.
        url: OWS endpoint URL.  Defaults to config ``ows.wfs_nuts.url``.
        name_field: Attribute column to filter on.  Defaults to config.
        typename: WFS layer name.  Defaults to config.

    Returns:
        GeoDataFrame or None on network / parse failure.
    """
    from processes.config import get_config

    cfg = get_config()
    wfs_nuts = cfg.wfs_nuts

    if url is None:
        url = wfs_nuts.url
    if typename is None:
        typename = wfs_nuts.layer
    if name_field is None:
        name_field = wfs_nuts.name_field

    cql_literal = _to_cql_literal(filtervalue)
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typename": typename,
        "outputFormat": "application/json",
        "cql_filter": f"{name_field} = {cql_literal}",
    }
    logger.info('Requesting WFS: %s', params)
    try:
        r = requests.get(url, params=params)
        r.raise_for_status()
        gdf = gpd.read_file(BytesIO(r.content))
        if gdf.empty:
            logger.warning('Empty result for %s where %s = %s', typename, name_field, filtervalue)
        else:
            logger.info('WFS filter OK: %s %s=%s (%d features)', typename, name_field, filtervalue, len(gdf))
    except Exception:
        logger.exception('WFS request failed for %s', typename)
        gdf = None
    return gdf