# -*- coding: utf-8 -*-
# Copyright notice
#   --------------------------------------------------------------------
#   Copyright (C) 2026 Deltares
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

# $HeadURL: https://svn.oss.deltares.nl/repos/openearthtools/trunk/python/applications/wps/ri2de/processes/utils_GeoServer.py $
# $Keywords: $

import os
import json
import time
import requests
from requests.auth import HTTPBasicAuth
from collections import defaultdict
import geopandas as gpd
from shapely.geometry import mapping
from pyproj import CRS, Transformer
from shapely.geometry import shape
from shapely.ops import transform
from shapely.wkt import loads, dumps

# conda packages
from geo.Geoserver import Geoserver, GeoserverException
from geoserver.catalog import FailedRequestError

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
            appconfig['sdi']['geoserver']['resturl'],
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
        """Create a GeoPackage-backed datastore via the REST API.

        Points GeoServer at the file on disk (no byte upload).
        The POST is synchronous — returns 200/201 on success.
        """
        if not os.path.isfile(gpkg_path):
            raise FileNotFoundError(gpkg_path)

        gpkg_abs_path = os.path.abspath(gpkg_path)
        endpoint = f"{self.url}/rest/workspaces/{ws}/datastores"

        payload = {
            "dataStore": {
                "name": store,
                "type": "GeoPackage",
                "enabled": True,
                "connectionParameters": {
                    "entry": [
                        {"@key": "database", "$": gpkg_abs_path},
                        {"@key": "dbtype", "$": "geopkg"},
                    ]
                },
            }
        }

        r = requests.post(endpoint, auth=self.auth,
                          headers=self.h_json,
                          data=json.dumps(payload), timeout=self.timeout)
        if r.status_code not in (200, 201):
            logging.error('Datastore creation failed: %s %s', r.status_code, r.text[:500])
            r.raise_for_status()
        logging.info('Datastore %s created (path: %s)', store, gpkg_abs_path)

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
    def publish_featuretype(self, ws, store, layer_name, title=None, native_name=None):
        """
        POST /workspaces/{ws}/datastores/{store}/featuretypes
        Body: {"featureType":{"name":"<layer_name>","title":"..."}}
        """
        payload = {"featureType": {"name": layer_name}}
        if title:
            payload["featureType"]["title"] = title
        if native_name:
            payload["featureType"]["nativeName"] = native_name
        
        logging.info(f"Publishing feature type '{layer_name}' in store '{store}'")
        r = requests.post(
            f"{self.url}/rest/workspaces/{ws}/datastores/{store}/featuretypes",
            auth=self.auth, headers=self.h_json,
            data=json.dumps(payload), timeout=self.timeout
        )
        
        if r.status_code not in [200, 201]:
            logging.error(f"Failed to publish feature type: {r.status_code} - {r.text}")
        r.raise_for_status()
        
        # Verify it was created
        verify_r = requests.get(
            f"{self.url}/rest/workspaces/{ws}/datastores/{store}/featuretypes/{layer_name}.json",
            auth=self.auth, timeout=self.timeout
        )
        if verify_r.status_code == 200:
            logging.info(f"✓ Feature type '{layer_name}' verified in GeoServer")
        else:
            logging.warning(f"Feature type published but verification failed: {verify_r.status_code}")

    # ---------- Delete a feature type ----------
    def delete_featuretype(self, ws, store, layer_name):
        """Delete a feature type from a datastore.

        Args:
            ws (str): workspace name
            store (str): datastore name
            layer_name (str): feature type name to delete
        """
        try:
            url = f"{self.url}/rest/workspaces/{ws}/datastores/{store}/featuretypes/{layer_name}"
            r = requests.delete(url, auth=self.auth, timeout=self.timeout)
            if r.status_code == 204:
                logging.info(f"✓ Feature type '{layer_name}' deleted from store '{store}'")
                return True
            elif r.status_code == 404:
                logging.warning(f"Feature type '{layer_name}' not found in store '{store}' (already deleted?)")
                return True
            else:
                logging.error(f"Failed to delete feature type '{layer_name}': {r.status_code} - {r.text}")
                return False
        except Exception as e:
            logging.error(f"Exception deleting feature type '{layer_name}': {str(e)}")
            return False
    
    # ---------- Trigger GeoServer catalog reload ----------
    def reload_catalog(self):
        """
        POST /rest/reload
        Forces GeoServer to reload its configuration catalog.
        This can help make newly created resources visible.
        """
        try:
            r = requests.post(
                f"{self.url}/rest/reload",
                auth=self.auth, timeout=self.timeout
            )
            if r.status_code == 200:
                logging.info("✓ GeoServer catalog reloaded successfully")
                return True
            else:
                logging.warning(f"Catalog reload returned: {r.status_code}")
                return False
        except Exception as e:
            logging.warning(f"Failed to reload catalog: {e}")
            return False
    
    # ---------- Explicitly ensure layer resource exists ----------
    def ensure_layer_resource(self, ws, layer_name):
        """
        Explicitly create a layer resource if it doesn't exist.
        Sometimes GeoServer doesn't auto-create the layer when publishing a featureType.
        
        In GeoServer 2.28.x, layers may not be automatically created from feature types.
        This method ensures the layer exists by checking and creating if necessary.
        """
        # First check if it exists
        logging.info(f"Checking if layer resource '{layer_name}' exists in workspace '{ws}'...")
        r = requests.get(
            f"{self.url}/rest/workspaces/{ws}/layers/{layer_name}.json",
            auth=self.auth, timeout=self.timeout
        )
        if r.status_code == 200:
            logging.info(f"✓ Layer resource '{layer_name}' already exists in workspace '{ws}'")
            return True
        elif r.status_code == 404:
            logging.info(f"Layer resource does not exist, will attempt to create it")
        else:
            logging.warning(f"Unexpected response checking layer: {r.status_code}")
        
        # Option 1: Try without explicit resource reference (let GeoServer auto-link)
        # This works better in some GeoServer versions
        payload_simple = {
            "layer": {
                "name": layer_name
            }
        }
        
        try:
            logging.info(f"Attempting to create layer resource with simple payload...")
            r = requests.post(
                f"{self.url}/rest/workspaces/{ws}/layers",
                auth=self.auth, headers=self.h_json,
                data=json.dumps(payload_simple), timeout=self.timeout
            )
            if r.status_code in [200, 201]:
                logging.info(f"✓ Successfully created layer resource for '{layer_name}'")
                return True
            else:
                logging.warning(f"Simple payload failed: {r.status_code} - {r.text}")
        except Exception as e:
            logging.warning(f"Simple payload exception: {e}")
        
        # Option 2: Try with explicit resource reference
        payload_detailed = {
            "layer": {
                "name": layer_name,
                "resource": {
                    "name": f"{ws}:{layer_name}"
                }
            }
        }
        
        try:
            logging.info(f"Attempting to create layer resource with detailed payload...")
            r = requests.post(
                f"{self.url}/rest/workspaces/{ws}/layers",
                auth=self.auth, headers=self.h_json,
                data=json.dumps(payload_detailed), timeout=self.timeout
            )
            if r.status_code in [200, 201]:
                logging.info(f"✓ Successfully created layer resource for '{layer_name}' (detailed payload)")
                return True
            else:
                logging.error(f"Detailed payload failed: {r.status_code} - {r.text}")
                return False
        except Exception as e:
            logging.error(f"Detailed payload exception: {e}")
            return False

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

    # ---------- Verify layer exists and is ready ----------
    def layer_exists(self, ws, layer_name, max_wait=10):
        """
        GET /rest/workspaces/{ws}/layers/{layer_name}.json
        Returns True if layer exists and is accessible
        Waits up to max_wait seconds for the layer to become available
        """
        start_time = time.time()
        attempt = 0
        while time.time() - start_time < max_wait:
            attempt += 1
            r = requests.get(
                f"{self.url}/rest/workspaces/{ws}/layers/{layer_name}.json",
                auth=self.auth, timeout=self.timeout
            )
            if r.status_code == 200:
                logging.info(f"Layer '{layer_name}' found in workspace '{ws}' after {attempt} attempts")
                logging.info(f"Layer details: {r.json()}")
                return True
            elif r.status_code == 404:
                logging.info(f"Layer '{layer_name}' not yet available (attempt {attempt}), waiting...")
                time.sleep(1)
            else:
                logging.warning(f"Unexpected status {r.status_code} when checking layer '{layer_name}': {r.text}")
                time.sleep(1)
        
        logging.error(f"Layer '{layer_name}' did not become available after {max_wait} seconds")
        return False

    # ---------- Set default style on the LAYER (not the featureType) ----------
    def set_default_style(self, ws, layer_name, style_name, wait_for_layer=True, max_wait=5, skip_verification=False):
        """
        PUT /rest/workspaces/{ws}/layers/{layer_name}
        Body: {"layer":{"defaultStyle":{"name":"<style>"}}}
        """
        # First verify the layer exists and is accessible (wait up to max_wait seconds)
        # Can be skipped if layer was just created and verification is unreliable
        if wait_for_layer and not skip_verification:
            if not self.layer_exists(ws, layer_name, max_wait=max_wait):
                logging.warning(f"Layer '{layer_name}' verification failed, but attempting to set style anyway")
                # Don't raise - try to set style anyway
        
        # Check if style exists - try workspace-specific first, then global
        style_ws = None
        if self.style_exists(style_name, ws=ws):
            style_ws = ws
            logging.info(f"Style '{style_name}' found in workspace '{ws}'")
        elif self.style_exists(style_name):
            logging.info(f"Style '{style_name}' found in global styles")
        else:
            raise RuntimeError(f"Style '{style_name}' does not exist in workspace '{ws}' or global styles")
        
        # Build payload - include workspace if style is workspace-specific
        if style_ws:
            payload = {"layer": {"defaultStyle": {"name": style_name, "workspace": style_ws}}}
        else:
            payload = {"layer": {"defaultStyle": {"name": style_name}}}
        
        logging.info(f"Setting style payload: {json.dumps(payload)}")
        r = requests.put(
            f"{self.url}/rest/workspaces/{ws}/layers/{layer_name}",
            auth=self.auth, headers=self.h_json,
            data=json.dumps(payload), timeout=self.timeout
        )
        if r.status_code != 200:
            error_detail = r.text if r.text else "No error details"
            logging.error(f"GeoServer style error response (Status {r.status_code}): {error_detail}")
            logging.error(f"Request URL: {self.url}/rest/workspaces/{ws}/layers/{layer_name}")
            logging.error(f"Request payload: {json.dumps(payload)}")
        r.raise_for_status()

    def delete_layer(self, ws, layer_name):
        """Delete a layer from a workspace.
        
        Args:
            ws (str): workspace name
            layer_name (str): layer name to delete
        """
        try:
            url = f"{self.url}/rest/workspaces/{ws}/layers/{layer_name}"
            r = requests.delete(url, auth=self.auth, timeout=self.timeout)
            if r.status_code == 204:  # No Content = success
                logging.info(f"✓ Layer '{layer_name}' deleted from workspace '{ws}'")
                return True
            elif r.status_code == 404:
                logging.warning(f"Layer '{layer_name}' not found in workspace '{ws}' (already deleted?)")
                return True  # Treat as success since it's gone anyway
            else:
                logging.error(f"Failed to delete layer '{layer_name}': {r.status_code} - {r.text}")
                return False
        except Exception as e:
            logging.error(f"Exception deleting layer '{layer_name}': {str(e)}")
            return False

    def delete_datastore(self, ws, store_name, recursive=True):
        """Delete a datastore from a workspace.
        
        Args:
            ws (str): workspace name
            store_name (str): datastore name to delete
            recursive (bool): if True, delete the datastore even if it has layers
        """
        try:
            url = f"{self.url}/rest/workspaces/{ws}/datastores/{store_name}"
            if recursive:
                url += "?recurse=true"
            
            r = requests.delete(url, auth=self.auth, timeout=self.timeout)
            if r.status_code == 204:  # No Content = success
                logging.info(f"✓ Datastore '{store_name}' deleted from workspace '{ws}'")
                return True
            elif r.status_code == 404:
                logging.warning(f"Datastore '{store_name}' not found in workspace '{ws}' (already deleted?)")
                return True  # Treat as success since it's gone anyway
            else:
                logging.error(f"Failed to delete datastore '{store_name}': {r.status_code} - {r.text}")
                return False
        except Exception as e:
            logging.error(f"Exception deleting datastore '{store_name}': {str(e)}")
            return False

    def delete_layer_and_store(self, ws, store_name):
        """Delete both the datastore and its associated layers.
        
        Args:
            ws (str): workspace name
            store_name (str): datastore/store name to clean up
        """
        # First delete the datastore recursively (which will remove all layers)
        return self.delete_datastore(ws, store_name, recursive=True)

def republish_layer(store='hexagons_17727241142485569', 
                    layer_name='hexagons_17727241142485569_td', 
                    title=None, 
                    native_name=None, 
                    style_name='transport_density', 
                    workspace='tmp',
                    wait_for_layer=True, 
                    max_wait=5):
    """
    Publish a new layer from an existing datastore with a specific style.
    This allows you to publish multiple layers from the same GPKG store with different styles.
    
    Args:
        store (str): Existing datastore name (default: 'hexagons_17727241142485569')
        layer_name (str): New layer name to publish (default: 'hexagons_17727241142485569_td')
        title (str): Optional layer title
        native_name (str): Native feature type name in the datastore (default: same as store)
        style_name (str): Style to apply (default: 'transport_density')
        workspace (str): GeoServer workspace (default: 'tmp')
        wait_for_layer (bool): Wait for layer to be available before setting style
        max_wait (int): Maximum seconds to wait for layer availability
    
    Returns:
        bool: True if successful, False otherwise
    """
    # Configuration for GeoServer    
    appconfig = read_appyml('app.yml')
    geoserver_url = appconfig['sdi']['geoserver']['resturl']
    username = appconfig['sdi']['geoserver']['user']
    password = appconfig['sdi']['geoserver']['password']

    try:
        # Initialize GS client
        gs = GS(geoserver_url, username, password)
        
        # Ensure workspace exists
        gs.ensure_workspace(workspace)
        logging.info(f"!-- republish_layer: Workspace '{workspace}' ensured")
        
        # Publish new layer from existing datastore
        logging.info(f"!-- republish_layer: Publishing new layer '{layer_name}' from existing store '{store}'")
        gs.publish_featuretype(
            ws=workspace,
            store=store,
            layer_name=layer_name,
            title=title,
            native_name=native_name or store  # Default to store name if not specified
        )
        
        # Reload catalog to ensure changes are visible
        gs.reload_catalog()
        time.sleep(1)
        
        # Set the style for the new layer
        if style_name:
            logging.info(f"!-- republish_layer: Setting style '{style_name}' for new layer '{layer_name}'")
            gs.set_default_style(
                ws=workspace,
                layer_name=layer_name,
                style_name=style_name,
                wait_for_layer=wait_for_layer,
                max_wait=max_wait,
                skip_verification=False
            )
        
        logging.info(f"!-- republish_layer: Layer '{layer_name}' published successfully with style '{style_name}'")
        return True
        
    except Exception as e:
        logging.error(f"!-- republish_layer: Failed to publish layer '{layer_name}': {e}")
        return False


def publish_gpkg(
    gpkg_path,
    workspace='tmp',
    style_name='hexagon_transparant',
    set_default_style=True,
    republish=False,
    datastore_name=None,
    layer_name=None,
    scan_timeout=30,
):
    """Upload a GeoPackage to GeoServer, publish its layers, and set a style.

    Optimised path: datastore creation is synchronous so we poll for
    available feature types with short intervals instead of fixed sleeps.
    """
    from processes.config import get_config

    cfg = get_config()
    geoserver_url = cfg.geoserver.resturl
    username = cfg.geoserver.user
    password = cfg.geoserver.password
    lname = os.path.basename(gpkg_path).replace('.gpkg', '')
    datastore = datastore_name or lname

    gs = GS(geoserver_url, username, password)
    gs.ensure_workspace(workspace)

    gs.upload_gpkg_datastore(workspace, datastore, gpkg_path,
                             configure="none", update="overwrite")

    # Poll for available feature types (short interval, bounded timeout)
    available = []
    deadline = time.time() + scan_timeout
    while time.time() < deadline:
        try:
            available = gs.list_available_featuretypes(workspace, datastore)
            if available:
                break
        except Exception:
            pass
        time.sleep(0.3)

    # Fallback: read layer names directly from the GPKG file
    if not available:
        import fiona
        available = fiona.listlayers(gpkg_path)
        logging.info('publish_gpkg: layers from GPKG file: %s', available)

    if not available:
        raise RuntimeError('No feature types found in GeoServer or GPKG file')

    published_layers = []
    for ft_name in available:
        ft_name = str(ft_name).strip()
        if not ft_name:
            continue

        publish_name = layer_name if (layer_name and len(available) == 1) else ft_name

        if republish:
            gs.delete_layer(workspace, publish_name)
            gs.delete_featuretype(workspace, datastore, publish_name)

        gs.publish_featuretype(
            ws=workspace,
            store=datastore,
            layer_name=publish_name,
            native_name=ft_name if publish_name != ft_name else None,
        )
        published_layers.append(publish_name)

        if style_name:
            try:
                gs.set_default_style(workspace, publish_name, style_name,
                                     wait_for_layer=True, max_wait=5,
                                     skip_verification=False)
            except Exception as exc:
                logging.warning('Style %s not set for %s: %s', style_name, publish_name, exc)

    logging.info('publish_gpkg: published %s', published_layers)
    return published_layers


def createvieweroutput(wmslay, folder, jsontitles, wmsurl):
    """Build the viewer-compatible layer catalogue structure.

    Returns:
        list[dict]: one entry per layer group, ready for JSON serialisation.
    """
    res_dict = defaultdict(list)

    for lname in wmslay:
        parts = lname.split('_')
        if len(parts) < 2:
            name = folder
            title = next(iter(jsontitles.values()))
        else:
            name = parts[1]
            title = jsontitles.get(name, name)

        res_dict[name].append({
            "name": title,
            "layer": f"tmp:{lname}",
            "url": f"{wmsurl}/wms",
        })

    return [{"folder": folder, "contents": entries} for entries in res_dict.values()]


def filtervectorbyvector(geoserver_url,filtergdf,filter_crs,kcslayer,kcs_crs):
    # Define the URL and layers
    try:
        # Validate input parameters
        logging.info(f'!--- filtering vector data: Starting with layer={kcslayer}, filter_crs={filter_crs}, wfslayer_crs={kcs_crs}')
        
        if filtergdf is None or filtergdf.empty:
            logging.error(f'! -- filtering vector data: filtergdf is None or empty')
            return None
        
        logging.info(f'!--- filtering vector data: filtergdf has {len(filtergdf)} feature(s), CRS={filtergdf.crs}')
        
        filter_epsg = filtergdf.crs.to_epsg() if filtergdf.crs else None
        if filter_epsg != kcs_crs:
            # Use GeoPandas to_crs for proper CRS transformation
            nuts_gdf = filtergdf.to_crs(epsg=kcs_crs)
            logging.info(f'!--- filtering vector data: filtergdf converted from EPSG:{filter_epsg} to EPSG:{kcs_crs}')
        else:
            nuts_gdf = filtergdf
            logging.info(f'!--- filtering vector data: No CRS conversion needed, both are EPSG:{kcs_crs}')
        
        # Validate geometry before creating WKT
        geom = nuts_gdf.geometry.iloc[0]
        if geom is None or geom.is_empty:
            logging.error(f'! -- filtering vector data: Geometry is None or empty')
            return None
        
        if not geom.is_valid:
            logging.warning(f'! -- filtering vector data: Geometry is invalid, attempting to fix')
            geom = geom.buffer(0)  # Try to fix invalid geometry
        
        # Keep WKT compact to avoid very large filter payloads.
        wkt_representation = dumps(geom, rounding_precision=6, trim=True)

        # If still very large, simplify slightly while preserving topology.
        if len(wkt_representation) > 12000:
            minx, miny, maxx, maxy = geom.bounds
            span = max(maxx - minx, maxy - miny)
            tolerance = max(span * 0.0001, 1e-06)
            simplified_geom = geom.simplify(tolerance, preserve_topology=True)
            wkt_representation = dumps(simplified_geom, rounding_precision=6, trim=True)
            logging.info(f'!--- filtering vector data: Simplified geometry for filter, tolerance={tolerance}')

        logging.info(f'!--- filtering vector data: WKT length: {len(wkt_representation)} chars')
        logging.info(f'!--- filtering vector data: WKT preview: {wkt_representation[:200]}...')
        
    except Exception as e:
        logging.error(f'! -- filtering vector data: transformer/WKT creation failed with {str(e)}')
        return None

    
    # Get the roads within the NUTS region
    kcs_params = {
        'service': 'WFS',
        'version': '2.0.0',
        'request': 'GetFeature',
        'typeNames': kcslayer,
        'outputFormat': 'application/json',
        'CQL_FILTER': f"Intersects(geom, SRID={kcs_crs};{wkt_representation})"
    }

    # Log the request for debugging
    logging.info(f'!--- filtering vector data: GeoServer URL: {geoserver_url}')
    logging.info(f'!--- filtering vector data: Request method: POST (form-encoded body)')
    logging.info(f'!--- filtering vector data: CQL length: {len(kcs_params["CQL_FILTER"])} chars')
    logging.info(f'!--- filtering vector data: Request params (without full CQL): service={kcs_params["service"]}, version={kcs_params["version"]}, request={kcs_params["request"]}, typeNames={kcs_params["typeNames"]}')
    
    try:
        # Use POST to avoid "414 URI Too Long" for large polygon filters.
        kcs_response = requests.post(geoserver_url, data=kcs_params, timeout=120)

        # Fallback for servers that do not allow KVP POST.
        if kcs_response.status_code in (405, 501):
            logging.warning(f'! -- filtering vector data: POST not supported ({kcs_response.status_code}), falling back to GET')
            kcs_response = requests.get(geoserver_url, params=kcs_params, timeout=120)
        
        # Check HTTP status code first
        logging.info(f'!--- filtering vector data: Response status code: {kcs_response.status_code}')
        
        if kcs_response.status_code != 200:
            logging.error(f'! -- filtering vector data: HTTP error {kcs_response.status_code}')
            logging.error(f'! -- filtering vector data: Response text: {kcs_response.text[:500]}')
            return None
        
        # Check content type
        content_type = kcs_response.headers.get('Content-Type', '')
        logging.info(f'!--- filtering vector data: Response content type: {content_type}')
        
        # Log first part of response for debugging
        response_preview = kcs_response.text[:200] if kcs_response.text else 'Empty response'
        logging.info(f'!--- filtering vector data: Response preview: {response_preview}')
        
        # Try to parse JSON
        try:
            kcs_data = kcs_response.json()
        except ValueError as ve:
            logging.error(f'! -- filtering vector data: JSON parsing failed: {ve}')
            logging.error(f'! -- filtering vector data: Full response text: {kcs_response.text[:1000]}')
            return None
        
        # Check if response contains features
        if 'features' not in kcs_data:
            logging.error(f'! -- filtering vector data: No features in response. Response keys: {kcs_data.keys()}')
            if 'exceptions' in kcs_data or 'exception' in kcs_data:
                logging.error(f'! -- filtering vector data: GeoServer exception: {kcs_data}')
            return None
        
        logging.info(f'!--- filtering vector data: {kcslayer} filtered by filtergdf, found {len(kcs_data.get("features", []))} features')
        
    except GeoserverException as ge:
        logging.error(f'! -- filtering vector data failed with Geoserverexception {ge}')
        return None
    except Exception as e:
        logging.error(f'! -- filtering vector data with nuts_gdf failed with {e}')
        return None
    
    # Create a GeoDataFrame from the roads data
    try:
        if not kcs_data.get('features'):
            logging.warning(f'!--- filtering vector data: No features returned from query')
            return gpd.GeoDataFrame()  # Return empty GeoDataFrame instead of None
        
        # Check if CRS info is in the response
        response_crs = kcs_data.get('crs')
        if response_crs:
            logging.info(f'!--- filtering vector data: Response CRS: {response_crs}')
        
        kcs_gdf = gpd.GeoDataFrame.from_features(kcs_data['features'], crs=CRS.from_epsg(kcs_crs))
        logging.info(f'!--- filtering vector data: Created GeoDataFrame with {len(kcs_gdf)} features, CRS={kcs_gdf.crs}')
        return kcs_gdf
    
    except Exception as e:
        logging.error(f'! -- filtering vector data: Failed to create GeoDataFrame from features: {e}')
        logging.error(f'! -- filtering vector data: Features data: {kcs_data.get("features", [])[:2]}')  # Log first 2 features
        return None
