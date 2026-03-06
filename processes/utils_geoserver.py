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
        """
        Uses /workspaces/{ws}/datastores/{store}/file.gpkg (PUT)
        to upload the file and (optionally) configure the store.
        See REST 'datastores' endpoints with file/url/external. 
        
        Two modes:
        1. If file is on same server as GeoServer: use file:// URL (faster, more reliable)
        2. Otherwise: upload bytes (may be async on some GeoServer instances)
        """
        # validate file
        if not os.path.isfile(gpkg_path):
            raise FileNotFoundError(gpkg_path)
        
        # Verify GPKG is readable and contains layers
        file_size = os.path.getsize(gpkg_path)
        logging.info(f"Uploading GPKG: {gpkg_path} (size: {file_size} bytes)")
        
        try:
            import geopandas as gpd
            test_gdf = gpd.read_file(gpkg_path)
            logging.info(f"GPKG verified: {len(test_gdf)} features, CRS: {test_gdf.crs}")
            
            # Also verify the file is actually readable as GPKG using fiona/GDAL
            import fiona
            layers = fiona.listlayers(gpkg_path)
            logging.info(f"GPKG contains {len(layers)} layer(s): {layers}")
            
            if not layers:
                raise RuntimeError("GPKG file has no layers!")
            
            # Ensure file is fully written and closed - important for network filesystems
            # Force a sync to disk
            import subprocess
            if os.name != 'nt':  # Linux
                try:
                    subprocess.run(['sync'], check=False, timeout=5)
                    logging.info("Forced filesystem sync")
                except:
                    pass
                    
        except Exception as e:
            logging.error(f"GPKG file validation failed: {e}")
            raise RuntimeError(f"Invalid GPKG file: {e}")

        # Don't use /file.gpkg endpoint - it always copies the file
        # Instead, create datastore via JSON with explicit database path
        # This matches what the manual UI does when referencing an existing file
        
        gpkg_abs_path = os.path.abspath(gpkg_path)
        logging.info(f"Creating datastore with database path: {gpkg_abs_path}")
        
        # Create datastore via POST with JSON configuration
        endpoint = f"{self.url}/rest/workspaces/{ws}/datastores"
        
        payload = {
            "dataStore": {
                "name": store,
                "type": "GeoPackage",
                "enabled": True,
                "connectionParameters": {
                    "entry": [
                        {"@key": "database", "$": gpkg_abs_path},
                        {"@key": "dbtype", "$": "geopkg"}
                    ]
                }
            }
        }
        
        logging.info(f"Creating datastore at: {endpoint}")
        logging.info(f"Payload: {json.dumps(payload, indent=2)}")
        
        r = requests.post(endpoint, auth=self.auth,
                         headers=self.h_json,
                         data=json.dumps(payload), timeout=self.timeout)
        
        logging.info(f"Datastore creation response: status={r.status_code}, body={r.text[:500] if r.text else 'empty'}")
        
        # POST to /datastores should be synchronous (200/201)
        if r.status_code in [200, 201]:
            logging.info(f"✓ Datastore created successfully with explicit database path")
            # Verify the datastore was created with correct path
            verify_url = f"{self.url}/rest/workspaces/{ws}/datastores/{store}.json"
            verify_r = requests.get(verify_url, auth=self.auth, timeout=self.timeout)
            if verify_r.status_code == 200:
                datastore_info = verify_r.json()
                conn_params = datastore_info.get('dataStore', {}).get('connectionParameters', {})
                logging.info(f"Datastore connection parameters: {json.dumps(conn_params, indent=2)}")
                
                # Extract and verify database path
                db_path = None
                if 'entry' in conn_params:
                    for entry in conn_params['entry']:
                        if entry.get('@key') == 'database':
                            db_path = entry.get('$')
                            break
                
                if db_path == gpkg_abs_path:
                    logging.info(f"✓ Database path confirmed correct: {db_path}")
                else:
                    logging.warning(f"⚠ Database path mismatch! Expected: {gpkg_abs_path}, Got: {db_path}")
            else:
                logging.warning(f"Could not verify datastore: {verify_r.status_code}")
            return
        else:
            # Error response
            logging.error(f"Failed to create datastore: {r.status_code} - {r.text}")
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


def publish_gpkg(
    gpkg_path,
    workspace='tmp',
    style_name='hexagon_transparant',         # e.g., "hexagon_transparant"
    set_default_style=True,
    delay_after_upload=2,     # seconds; allow GS to scan and configure store
    republish=False,
    datastore_name=None,
    layer_name=None
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
    geoserver_url = appconfig['sdi']['geoserver']['resturl']
    username = appconfig['sdi']['geoserver']['user']
    password = appconfig['sdi']['geoserver']['password']
    lname = os.path.basename(gpkg_path).replace('.gpkg','')
    datastore = datastore_name or lname
    
    timeout = 300
    scan_interval = 1
    layer_wait_timeout = 30  # Wait up to 30 seconds for layers to become available

    try:
        gdf = gpd.read_file(gpkg_path)
        crs = gdf.crs
        logging.info(f"!-- publish_gpkg: GeoPackage read successfully CRS: {gdf.crs}"  )
    except Exception as e:
        logging.error(f"!-- publish_gpkg: Failed to read GeoPackage {gpkg_path}: {e}")
        raise RuntimeError(f"Failed to read GeoPackage: {e}")
    
    try:
        gs = GS(geoserver_url, username, password)
        gs.ensure_workspace(workspace)  # create if missing  (REST workspaces)  # ref
        # (Workspaces endpoint is under the GeoServer REST umbrella)  # [5](https://docs.geoserver.org/stable/en/user/rest/)
    except Exception as e:
        logging.error(f"!-- publish_gpkg: Failed to connect to GeoServer or ensure workspace: {e}")
        raise RuntimeError(f"GeoServer connection/workspace error: {e}")
    except GeoserverException as ge:    
        logging.error(f"!-- publish_gpkg: GeoserverException while ensuring workspace: {ge}")
        raise RuntimeError(f"GeoServer workspace error: {ge}")

    # Upload GeoPackage to store
    try:
        # Use configure="none" - don't auto-configure layers, we'll do it manually
        # This works better with async (202) uploads where configure="first" may fail
        gs.upload_gpkg_datastore(workspace, datastore, gpkg_path,
                                configure="none", update="overwrite")
        # The /datastores ... /file.gpkg endpoint accepts the file bytes and
        # creates/updates the file-based store.  # [1](https://docs.geoserver.org/stable/en/user/rest/api/datastores.html)
        
        # Allow GeoServer time to scan and configure the datastore
        time.sleep(delay_after_upload)
        logging.info(f"!-- publish_gpkg: GPKG uploaded with configure=none,will manually publish layers")
        
        # Immediately check if GeoServer can see any layers in the datastore
        try:
            test_available = gs.list_available_featuretypes(workspace, datastore)
            logging.info(f"!-- publish_gpkg: Available layers immediately after upload: {test_available}")
        except Exception as e:
            logging.warning(f"!-- publish_gpkg: Could not list available layers after upload: {e}")
    except Exception as e:
        logging.error(f"!-- publish_gpkg: Failed to upload GeoPackage to GeoServer: {e}")
        raise RuntimeError(f"GeoServer upload error: {e}")  
    except GeoserverException as ge:
        logging.error(f"!-- publish_gpkg: GeoserverException while uploading GeoPackage: {ge}")
        raise RuntimeError(f"GeoServer upload error: {ge}")


    # -------------------------------------------
    # 2. Wait for GeoServer to scan available feature types
    # -------------------------------------------
    logging.info("!-- publish_gpkg: Waiting for GeoServer to detect feature types...")

    deadline = time.time() + timeout
    available = []

    # Since we used configure="none", we need to check for AVAILABLE (not configured) feature types
    while time.time() < deadline:
        try:
            available = gs.list_available_featuretypes(workspace, datastore)
            if available:
                logging.info(f"!-- publish_gpkg: Found available feature types: {available}")
                break
        except FailedRequestError:
            logging.warning("!-- publish_gpkg: GeoServer not ready yet (FailedRequestError), retrying...")
        except Exception as e:
            logging.warning(f"!-- publish_gpkg: Error checking available types: {e}")

        time.sleep(scan_interval)

    # Fallback: list configured types if "available" is empty
    if not available:
        logging.warning("!-- publish_gpkg: No 'available' feature types found — checking configured types.")
        url = f"{geoserver_url}/rest/workspaces/{workspace}/datastores/{datastore}/featuretypes.json"

        r = requests.get(url, auth=HTTPBasicAuth(username, password), timeout=60)
        r.raise_for_status()
        data = r.json()
        logging.info(f"!-- publish_gpkg: Raw featureTypes response: {json.dumps(data, indent=2)}")

        if "featureTypes" in data:
            ft_data = data["featureTypes"]
            # Handle different response formats from GeoServer
            if isinstance(ft_data, dict):
                # Standard response: {"featureType": [...]}
                available = [ft["name"] for ft in ft_data.get("featureType", []) if ft.get("name")]
            elif isinstance(ft_data, str):
                # Single layer name as string - only add if non-empty
                if ft_data.strip():
                    logging.info(f"!-- publish_gpkg: featureTypes is a string: '{ft_data}'")
                    available = [ft_data]
                else:
                    logging.warning(f"!-- publish_gpkg: featureTypes is an empty string")
            elif isinstance(ft_data, list):
                # List of layer names - filter out empty strings
                available = [name for name in ft_data if name and str(name).strip()]
            else:
                logging.warning(f"!-- publish_gpkg: Unexpected featureTypes format: {type(ft_data)}")

    # Last resort: read layer names directly from GPKG
    if not available:
        logging.warning("!-- publish_gpkg: No feature types from GeoServer — reading layers from GPKG directly.")
        try:
            import fiona
            available = fiona.listlayers(gpkg_path)
            logging.info(f"!-- publish_gpkg: Found layers in GPKG: {available}")
        except Exception as e:
            logging.error(f"!-- publish_gpkg: Failed to read layers from GPKG: {e}")
    
    if not available:
        raise RuntimeError("!-- publish_gpkg: No feature types found — GeoServer did not scan the GPKG and could not read from file.")

    # -------------------------------------------
    # 3. Publish each layer manually
    # -------------------------------------------
    published_layers = []

    for ft_name in available:
        # Skip empty or whitespace-only names
        if not ft_name or not str(ft_name).strip():
            logging.warning(f"!-- publish_gpkg: Skipping empty layer name")
            continue
        
        ft_name = str(ft_name).strip()

        if layer_name:
            if len(available) == 1:
                publish_name = layer_name
            else:
                publish_name = f"{layer_name}_{ft_name}"
        else:
            publish_name = ft_name

        if republish:
            logging.info(f"!-- publish_gpkg: Republish enabled, deleting existing layer/feature type '{publish_name}'")
            gs.delete_layer(workspace, publish_name)
            gs.delete_featuretype(workspace, datastore, publish_name)
        
        # Manually publish the feature type
        logging.info(f"!-- publish_gpkg: Publishing layer: '{publish_name}' (native: '{ft_name}')")
        try:
            gs.publish_featuretype(
                ws=workspace,
                store=datastore,
                layer_name=publish_name,
                native_name=ft_name if publish_name != ft_name else None
            )
            logging.info(f"!-- publish_gpkg: Successfully published feature type: {publish_name}")
            
            # Trigger a catalog reload to ensure GeoServer recognizes the new feature type
            gs.reload_catalog()
            time.sleep(2.0)  # Give GeoServer time to process the reload
            
            # Explicitly ensure layer resource exists
            logging.info(f"!-- publish_gpkg: Ensuring layer resource exists for: {publish_name}")
            layer_created = gs.ensure_layer_resource(workspace, publish_name)
            
            if layer_created:
                logging.info(f"!-- publish_gpkg: Layer resource confirmed for {ft_name}")
            else:
                logging.warning(f"!-- publish_gpkg: Could not create/verify layer resource for {ft_name}")
            
            published_layers.append(publish_name)

        except Exception as e:
            logging.error(f"!-- publish_gpkg: Failed to publish {ft_name}: {e}")
            raise
        
        # Try to set style, but don't fail if it doesn't work
        if style_name:
            # Add a longer delay to ensure layer is fully registered
            # Deployment servers may take longer to make layers discoverable
            time.sleep(3.0)  # Increased from 1.0s for deployment servers
            
            try:
                logging.info(f"!-- publish_gpkg: Setting default style '{style_name}' for layer: {publish_name}")
                # Skip verification since it's unreliable on deployment - just try to set the style
                # Layer should exist since we just created it and reloaded the catalog
                gs.set_default_style(workspace, publish_name, style_name, wait_for_layer=False, skip_verification=True)
                logging.info(f"!-- publish_gpkg: Successfully set style for {publish_name}")
                    
            except requests.exceptions.HTTPError as he:
                logging.warning(f"!-- publish_gpkg: HTTP error setting style for {publish_name}: {he}. Response: {he.response.text if hasattr(he, 'response') and he.response else 'No response'}. Layer is published but without style.")
            except Exception as e:
                logging.warning(f"!-- publish_gpkg: Failed to set style for {publish_name}: {e}. Layer is published but without style.")

    logging.info(f"!-- publish_gpkg: Successfully published layers: {published_layers}")
    return published_layers


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


def filtervectorbyvector(geoserver_url,filtergdf,filter_crs,kcslayer,kcs_crs):
    # Define the URL and layers
    try:
        # Validate input parameters
        logging.info(f'!--- filtering vector data: Starting with layer={kcslayer}, filter_crs={filter_crs}, kcs_crs={kcs_crs}')
        
        if filtergdf is None or filtergdf.empty:
            logging.error(f'! -- filtering vector data: filtergdf is None or empty')
            return None
        
        logging.info(f'!--- filtering vector data: filtergdf has {len(filtergdf)} feature(s), CRS={filtergdf.crs}')
        
        if filter_crs != kcs_crs:
            # Use GeoPandas to_crs for proper CRS transformation
            nuts_gdf = filtergdf.to_crs(epsg=kcs_crs)
            logging.info(f'!--- filtering vector data: filtergdf converted from {filter_crs} to {kcs_crs}')
        else:
            nuts_gdf = filtergdf
            logging.info(f'!--- filtering vector data: No CRS conversion needed, both are {kcs_crs}')
        
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
        
        kcs_gdf = gpd.GeoDataFrame.from_features(kcs_data['features'], crs=CRS.from_epsg(4326))
        logging.info(f'!--- filtering vector data: Created GeoDataFrame with {len(kcs_gdf)} features, CRS={kcs_gdf.crs}')
        return kcs_gdf
    
    except Exception as e:
        logging.error(f'! -- filtering vector data: Failed to create GeoDataFrame from features: {e}')
        logging.error(f'! -- filtering vector data: Features data: {kcs_data.get("features", [])[:2]}')  # Log first 2 features
        return None
