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
import json
import time
import requests
from requests.auth import HTTPBasicAuth
from collections import defaultdict

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
        logging.error(f"GeoserverException error, attempt to create workspace again: {ge}")
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
    dctstyles['drought']    = ("Drought mitigation",'drought')
    dctstyles['erosion']    = ("Erosion mitigation",'erosion')
    dctstyles['flood']    = ("Flood mitigation",'flood')

    # Initialize the geoserver
    try:
        geo = Geoserver(
            appconfig['sdi']['geoserver']['url'],
            username=appconfig['sdi']['geoserver']['user'],
            password=appconfig['sdi']['geoserver']['password'],
        )
        logging.info("!-- load2geoserver: connection to geoserver sussesfull")
    except Exception as e:
        logging.error(f"!-- load2geoserver: unable to connect to geoserver {str(e)}")

    # fetch workspaces and check if workspace aws is already setup in if necessary create it
    try:
        geo.get_workspaces()
        get_or_create_workspace(geo, aws)
        logging.info(f"!-- load2geoserver: Workspace exists: {aws}")
    except GeoserverException as ge:
        logging.error(f"!-- load2geoserver: Workspace GeoserverException: {ge}")
    except Exception as e:
        logging.error(f"!-- load2geoserver: Workspace general exception: {e}")

    # create emtpy list to harvest the wmslayers
    wmslayers = []

    for gtif in lstgtif:
        lname = os.path.basename(gtif).replace(".tif", "")
        style_key = lname.split('_')[1]
        sld_style = dctstyles.get(style_key, [None])[1]
        # For uploading raster data to the geoserver
        try:
            wmslay = f"{aws}:{lname}"
            wmslayers.append(wmslay)
            sld_style = dctstyles.get(style_key, [None])[1]
            geo.create_coveragestore(layer_name=lname, path=os.path.normpath(gtif), workspace=aws)
            geo.publish_style(layer_name=lname, style_name=sld_style, workspace=aws)
            logging.info(f"!-- load2geoserver: Coverage store created and style {sld_style} assigned for {lname}")
        except GeoserverException as ge:
            logging.error(f"!-- load2geoserver: Store and layer creation GeoserverException: {ge}")            
        except Exception as e:
            logging.info(f"!-- load2geoserver: Store and layer creation failed for {gtif},{str(e)}")

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

def clean_geoserver():
    from utils import read_appyml
    # clean the geoseover
    appconfig = read_appyml('app.yml')

    rest_url = appconfig['sdi']['geoserver']['url']
    username=appconfig['sdi']['geoserver']['user']
    password=appconfig['sdi']['geoserver']['password']
    workspace = 'tmp'

    cleanup_workspace_geoserver(rest_url, username, password, workspace)
    
    #get tmp dir and clean also
    tmpdir = appconfig['sid']['tmp']['tmpdir']
    # call the utils.clean_tmp function, but it should be adjusted to only clean tif and xml files.

class GS:
    # READ THIS:
    # quite a complicated, but clean part, necesarry due to the fact that geo.Geoserver package is not able to load geopackages
    def __init__(self, url, user, pwd, timeout=60):
        # url like "http://localhost:8080/geoserver"
        self.url = url.rstrip("/")
        self.auth = HTTPBasicAuth(user, pwd)
        self.timeout = timeout
        self.h_json = {"Content-Type": "application/json"}
        self.h_xml  = {"Content-Type": "application/xml"}  # may be handy

    # ---------- Workspace ----------
    def ensure_workspace(self, ws):
        r = requests.get(f"{self.url}/rest/workspaces/{ws}.json",
                         auth=self.auth, timeout=self.timeout)
        if r.status_code == 200:
            return
        if r.status_code == 404:
            payload = {"workspace": {"name": ws}}
            r = requests.post(f"{self.url}/rest/workspaces",
                              auth=self.auth, headers=self.h_json,
                              data=json.dumps(payload), timeout=self.timeout)
            r.raise_for_status()
        else:
            r.raise_for_status()

    # ---------- Upload GeoPackage as a datastore ----------
    def upload_gpkg_datastore(self, ws, store, gpkg_path,
                              configure="none", update="overwrite"):
        """
        Uses /workspaces/{ws}/datastores/{store}/file.gpkg (PUT)
        to upload the file and (optionally) configure the store.
        See REST 'datastores' endpoints with file/url/external. 
        """
        # validate file
        if not os.path.isfile(gpkg_path):
            raise FileNotFoundError(gpkg_path)

        endpoint = (f"{self.url}/rest/workspaces/{ws}/datastores/{store}"
                    f"/file.gpkg?configure={configure}&update={update}")
        # NOTE: 'configure' can be: none|all|first|append (depending on version);
        # we use 'none' then explicitly publish layers.
        with open(gpkg_path, "rb") as f:
            r = requests.put(endpoint, auth=self.auth,
                             headers={"Content-Type": "application/octet-stream"},
                             data=f, timeout=self.timeout)
        r.raise_for_status()

    # ---------- List available feature types in a store ----------
    def list_available_featuretypes(self, ws, store):
        """
        GET /workspaces/{ws}/datastores/{store}/featuretypes.json?list=available
        """
        r = requests.get(
            f"{self.url}/rest/workspaces/{ws}/datastores/{store}/featuretypes.json",
            params={"list": "available"}, auth=self.auth, timeout=self.timeout
        )
        r.raise_for_status()
        data = r.json()
        # Response structure varies: sometimes {'list': {'string': ['name', ...]}}
        # sometimes {'featureTypes': {'featureType': [...]}} for configured ones.
        names = []
        if "list" in data and "string" in data["list"]:
            items = data["list"]["string"]
            if isinstance(items, list):
                names = items
            elif isinstance(items, str):
                names = [items]
        return names

    # ---------- Publish a feature type ----------
    def publish_featuretype(self, ws, store, layer_name, title=None):
        """
        POST /workspaces/{ws}/datastores/{store}/featuretypes
        Body: {"featureType":{"name":"<layer_name>","title":"..."}}
        """
        payload = {"featureType": {"name": layer_name}}
        if title:
            payload["featureType"]["title"] = title
        r = requests.post(
            f"{self.url}/rest/workspaces/{ws}/datastores/{store}/featuretypes",
            auth=self.auth, headers=self.h_json,
            data=json.dumps(payload), timeout=self.timeout
        )
        r.raise_for_status()

    # ---------- Check if style exists (optionally in a workspace) ----------
    def style_exists(self, style_name, ws=None):
        if ws:
            url = f"{self.url}/rest/workspaces/{ws}/styles/{style_name}.json"
        else:
            url = f"{self.url}/rest/styles/{style_name}.json"
        r = requests.get(url, auth=self.auth, timeout=self.timeout)
        return r.status_code == 200

    # ---------- Upload SLD style (optional helper) ----------
    def upload_style_sld(self, style_name, sld_path, ws=None):
        """
        POST /rest/styles  (or /workspaces/{ws}/styles) with SLD mime.
        """
        if not os.path.isfile(sld_path):
            raise FileNotFoundError(sld_path)
        if ws:
            endpoint = f"{self.url}/rest/workspaces/{ws}/styles"
        else:
            endpoint = f"{self.url}/rest/styles"
        with open(sld_path, "rb") as f:
            r = requests.post(endpoint, params={"name": style_name},
                              auth=self.auth,
                              headers={"Content-Type": "application/vnd.ogc.sld+xml"},
                              data=f, timeout=self.timeout)
        r.raise_for_status()

    # ---------- Set default style on the LAYER (not the featureType) ----------
    def set_default_style(self, ws, layer_name, style_name):
        """
        PUT /rest/workspaces/{ws}/layers/{layer_name}
        Body: {"layer":{"defaultStyle":{"name":"<style>"}}}
        """
        payload = {"layer": {"defaultStyle": {"name": style_name}}}
        r = requests.put(
            f"{self.url}/rest/workspaces/{ws}/layers/{layer_name}",
            auth=self.auth, headers=self.h_json,
            data=json.dumps(payload), timeout=self.timeout
        )
        r.raise_for_status()


def publish_gpkg(
    gpkg_path,
    workspace='tmp',
    style_name='hexagon_transparant',         # e.g., "hexagon_transparant"
    set_default_style=True,
    delay_after_upload=1     # seconds; allow GS to scan store
):
    """
    End-to-end:
      - ensure workspace
      - upload .gpkg as datastore (using /file.gpkg)
      - list available layers
      - publish each
      - (optional) set default style for each published layer
    """
    # Configuration for GeoServer    
    appconfig = read_appyml('app.yml')
    geoserver_url = appconfig['sdi']['geoserver']['url']
    username = appconfig['sdi']['geoserver']['user']
    password = appconfig['sdi']['geoserver']['password']
    lname = os.path.basename(gpkg_path).replace('.gpkg','')
    datastore = lname

    gs = GS(geoserver_url, username, password)
    gs.ensure_workspace(workspace)  # create if missing  (REST workspaces)  # ref
    # (Workspaces endpoint is under the GeoServer REST umbrella)  # [5](https://docs.geoserver.org/stable/en/user/rest/)

    # Upload GeoPackage to store
    gs.upload_gpkg_datastore(workspace, datastore, gpkg_path,
                             configure="none", update="overwrite")
    # The /datastores ... /file.gpkg endpoint accepts the file bytes and
    # creates/updates the file-based store.  # [1](https://docs.geoserver.org/stable/en/user/rest/api/datastores.html)

    # Give GeoServer a moment to inspect the new store
    time.sleep(delay_after_upload)

    # Ask GeoServer which feature types are "available" in the store
    available = gs.list_available_featuretypes(workspace, datastore)
    # Feature types listing with ?list=available is the documented approach.  # [2](https://docs.geoserver.org/stable/en/user/rest/api/featuretypes.html)

    if not available:
        print("No 'available' feature types reported; trying 'all' as a fallback.")
        # Fallback: sometimes the store is already configured; fetch configured types
        r = requests.get(
            f"{geoserver_url.rstrip('/')}/rest/workspaces/{workspace}/datastores/{datastore}/featuretypes.json",
            auth=HTTPBasicAuth(username, password), timeout=60
        )
        r.raise_for_status()
        data = r.json()
        if "featureTypes" in data and "featureType" in data["featureTypes"]:
            available = [it["name"] for it in data["featureTypes"]["featureType"]]

    if not available:
        raise RuntimeError("GeoServer did not report any feature types in the GeoPackage store.")

    # Publish each layer (name must match the table/layer inside the GPKG)
    for name in available:
        try:
            gs.publish_featuretype(workspace, datastore, name, title=name)
            logging.info(f"Published layer: {workspace}:{name}")
        except requests.HTTPError as e:
            # If 409 or 400 occurs, it may already be configured—continue
            logging.error(f"Note: could not publish {name} ({e}). Continuing.")

        # Optionally set default style
        if style_name and set_default_style:
            if not gs.style_exists(style_name):
                logging.info(f"Style '{style_name}' not found in workspace '{workspace}'. Skipping style assignment.")
            else:
                gs.set_default_style(workspace, name, style_name)
                logging.info(f"Set default style '{style_name}' for layer {workspace}:{name}")
    return f'{workspace}:{name}'

def createvieweroutput(wmslay, folder, jsontitles, wmsurl):
    """creates specifc output for the map viewer environment 

    Args:
        wmslay (list)    : list of layers created in the geoserver
        folder (string)  : folder description for the viewer so it can aggregate the layers
        jsontitles (json): jsonobject with names and titles of the layer (so readable titles and technical names)
        wmsurl (string)  : url to the geoserver ows address

    Returns:
        json             : returns a json with a structure that is used in the viewer
    """

    logging.info(f"!-- create viewer input '{wmslay}', {folder}, {jsontitles}, {wmsurl}")
    res = []
    res_dict = defaultdict(list)  # <-- cleaner

    for lname in wmslay:
        parts = lname.split('_')
        if len(parts) < 2:
            logging.info(f"Layer name '{lname}' has no hazard part, {lname} will be used")
            name = folder
            title = next(iter(jsontitles.values()))
        else:
            name = parts[1]
            title = jsontitles.get(name, name)

        res_dict[name].append({
            "name": title,
            "layer": lname,
            "url": wmsurl
        })

    # Convert to desired structure
    for i, entries in res_dict.items():
        res.append({
            "folder": folder,
            "contents": entries
        })

    print(res)
    return json.dumps(res, indent=2)