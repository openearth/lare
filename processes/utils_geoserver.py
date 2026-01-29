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

# $HeadURL: https://svn.oss.deltares.nl/repos/openearthtools/trunk/python/applications/wps/ri2de/processes/utils_GeoServer.py $
# $Keywords: $

import os

# conda packages
from geo.Geoserver import Geoserver, GeoserverException

# local packages
from processes.utils import read_appyml

import logging
LOGGER= logging.getLogger("PYWPS")


def get_or_create_workspace(geo, aws):
    """Checks if a workspace exists, if not creates it and returns a workspace object

    Args:
        geo (object): the geoserver 
        aws (string): workspace name

    Returns:
        object: geo workspace object
    """
    try:
        ws = geo.get_workspace(workspace=aws)
        if ws is None:
            ws = geo.create_workspace(workspace=aws)
            logging.info(f"Workspace '{aws}' created")
        else:
            logging.info(f"Workspace '{aws}' already exists")
        return ws
    except GeoserverException as ge:
        logging.error(f"GeoserverException: {ge}")
        ws = geo.create_workspace(workspace=aws)
        logging.info(f"Workspace '{aws}' created")
        return ws
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        return None

# Upload raster file to GeoServer
def load2geoserver(lstgtif, sld_style="default", aws="tmp"):
    """Load gtif data into geoserver

    Args:
        cf (configparser obj)    : configparser object of the contents of a configuration file
        lstgtif (list)           : a list with gtif paths (incl. filenames)
        sld_style (str, optional): style name (shoul be there in geoserver) Defaults to 'brl'.
        aws (str, optional)      : Workspace, if give then will be created, otherwise defaults to 'abs'.

    Returns:
        List                     : of wmslayers
    """

    appconfig = read_appyml('app.yml')

    # we might want to use styles
    dctstyles = {}
    dctstyles['fire']    = ("Fire mitigation",'fire')
    dctstyles['heat']    = ("Heatwave mitigation",'heat')

    # Initialize the geoserver
    try:
        geo = Geoserver(
            appconfig['sdi']['geoserver']['url'],
            username=appconfig['sdi']['geoserver']['user'],
            password=appconfig['sdi']['geoserver']['password'],
        )
        logging.info("!-- load2geoserver: connection to geoserver sussesfull")
    except Exception as e:
        logging.info(f"!-- load2geoserver: unable to connect to geoserver {str(e)}")

    # fetch workspaces and check if workspace aws is already setup in if necessary create it
    try:
        geo.get_workspaces()
        get_or_create_workspace(geo, aws)
        logging.info(f"!-- Workspace exists: {aws}")
    except GeoserverException as ge:
        logging.error(f"!-- Workspace GeoserverException: {ge}")
    except Exception as e:
        logging.error(f"!-- Workspace general exception: {e}")

    # create emtpy list to harvest the wmslayers
    wmslayers = []

    for gtif in lstgtif:
        lname = os.path.basename(gtif).replace(".tif", "")
        
        logging.info(f'!-- create store and load tif: {gtif}')
        style_key = lname.split('_')[1]
        sld_style = dctstyles.get(style_key, [None])[1]
        logging.info(f'GTIF, set style for layer {os.path.normpath(gtif)}, {lname},{sld_style}')
        # For uploading raster data to the geoserver
        try:
            geo.create_coveragestore(layer_name=lname, path=os.path.normpath(gtif), workspace=aws)
            geo.publish_style(layer_name=lname, style_name=sld_style, workspace=aws)
            wmslay = f"{aws}:{lname}"
            wmslayers.append(wmslay)
            print(f"Coverage store created and style assigned for {lname}")
            sld_style = dctstyles.get(style_key, [None])[1]
            geo.create_coveragestore(layer_name=lname, path=os.path.normpath(gtif), workspace=aws)
            geo.publish_style(layer_name=lname, style_name=sld_style, workspace=aws)
            wmslay = f"{aws}:{lname}"
            wmslayers.append(wmslay)
            logging.info(f"Coverage store created and style {sld_style} assigned for {lname}")
        except GeoserverException as ge:
            logging.error(f"!-- Store and layer creation GeoserverException: {ge}")            
        except Exception as e:
            logging.info(f"!-- failed Store and layer creation  for {lname},{str(e)}")

        print(wmslay)
    #print("de wms layers", wmslayers)
    return wmslayers


def cleanup_workspace_geoserver(rest_url, username, password, workspace):
    """Deletes all layers and coverage stores in a single workspace using geo.Geoserver and also removes the data from
       the tmp folder

    Args:
        rest_url (string): url that is used to access the geoserver (wms_url in this case)
        username (string): username to enter geoserver
        password (string): password to enter geoserver 
        workspace (string): workspace to remove
    """
    # The geoserver-rest package requires the url that normally is used to access the geoserver (so not the thech url) 
    # and without the wms
    if (rest_url.endswith("/wms")):
        rest_url = rest_url.replace("/wms", "")

    try:
        geo = Geoserver(rest_url, username=username, password=password)
    except GeoserverException as e:
        print(f'Geoserver exception occured: {e}' )
    except Exception as e:
        print(f'some general execpetion while accessing geoserver: {e}')

    print(f"geoserver version: {geo.get_version()}")
    print(f"Cleaning workspace: {workspace}")

    # Try to get and delete layers
    try:
        layers = geo.get_layers(workspace=workspace)["layers"]
        if not layers:
            print(f" → No layers returned for workspace '{workspace}' (may be empty or inaccessible).")
        else:
            for layer in layers["layer"]:
                lname = layer["name"]
                print(f" → Deleting layer: {lname}")
                geo.delete_layer(layer_name=lname, workspace=workspace)
    except Exception as e:
        print(f" ✖ Failed to retrieve or delete layers in workspace '{workspace}': {e}")

    # Try to get and delete coverage stores
    try:
        stores = geo.get_coveragestores(workspace=workspace)["coverageStores"]
        if not stores:
            print(f" → No coverage stores returned for workspace '{workspace}' (may be empty or inaccessible).")
        else:
            for store in stores["coverageStore"]:
                store_name = store["name"]
                print(f" → Deleting coverage store: {store_name}")
                geo.delete_coveragestore(coveragestore_name=store_name, workspace=workspace)
    except Exception as e:
        print(f" ✖ Failed to retrieve or delete coverage stores in workspace '{workspace}': {e}")

def test():
    from utils import read_appyml
    # clean the geoseover
    appconfig = read_appyml('app.yml')

    rest_url = appconfig['sdi']['geoserver']['url']
    username=appconfig['sdi']['geoserver']['user']
    password=appconfig['sdi']['geoserver']['password']
    workspace = 'tmp'
    cleanup_workspace_geoserver(rest_url, username, password, workspace)


    