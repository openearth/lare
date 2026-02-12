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
        # First verify the style exists
        if not self.style_exists(style_name):
            raise RuntimeError(f"Style '{style_name}' does not exist")
        
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
    
    timeout = 30
    scan_interval = 1

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
        gs.upload_gpkg_datastore(workspace, datastore, gpkg_path,
                                configure="none", update="overwrite")
        # The /datastores ... /file.gpkg endpoint accepts the file bytes and
        # creates/updates the file-based store.  # [1](https://docs.geoserver.org/stable/en/user/rest/api/datastores.html)
        
        # Allow GeoServer time to scan the datastore
        time.sleep(delay_after_upload)
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

    while time.time() < deadline:
        try:
            available = gs.list_available_featuretypes(workspace, datastore)
            if available:
                logging.info(f"!-- publish_gpkg: Found available feature types: {available}")
                break
        except FailedRequestError:
            logging.warning("!-- publish_gpkg: GeoServer not ready yet (FailedRequestError), retrying...")
            pass

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
    # 3. Publish each layer
    # -------------------------------------------
    published_layers = []

    for ft_name in available:
        # Skip empty or whitespace-only names
        if not ft_name or not str(ft_name).strip():
            logging.warning(f"!-- publish_gpkg: Skipping empty layer name")
            continue
        
        ft_name = str(ft_name).strip()
        logging.info(f"!-- publish_gpkg: Publishing layer: '{ft_name}'")
        try:
            gs.publish_featuretype(
                ws=workspace,
                store=datastore,
                layer_name=ft_name
            )
            published_layers.append(ft_name)
            logging.info(f"!-- publish_gpkg: Successfully published feature type: {ft_name}")

        except Exception as e:
            logging.error(f"!-- publish_gpkg: Failed to publish {ft_name}: {e}")
            raise
        
        # Try to set style, but don't fail if it doesn't work
        if style_name:
            try:
                logging.info(f"!-- publish_gpkg: Setting default style '{style_name}' for layer: {ft_name}")
                gs.set_default_style(workspace, ft_name, style_name)
                logging.info(f"!-- publish_gpkg: Successfully set style for {ft_name}")
            except Exception as e:
                logging.warning(f"!-- publish_gpkg: Failed to set style for {ft_name}: {e}. Layer is published but without style.")

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
        if filter_crs != kcs_crs:
            # Define the CRS transformer
            project = Transformer.from_crs(filter_crs, kcs_crs, always_xy=True)

            # Transform the NUTS region geometry to CRS 4326
            nuts_geom = filtergdf.geometry.apply(lambda geom: transform(project.transform, geom))

            # Create a GeoDataFrame from the transformed geometry
            nuts_gdf = gpd.GeoDataFrame(geometry=nuts_geom, crs=CRS.from_epsg(kcs_crs))
        else:
            nuts_gdf = filtergdf
        wkt_representation = dumps(nuts_gdf.geometry.iloc[0])
        logging.info(f'!--- filtering vector data: filtergdf converted to {kcs_crs}')
    except Exception as e:
        logging.error(f'! -- filtering vector data: transformer failed with {str(e)}')

    
    # Get the roads within the NUTS region
    kcs_params = {
        'service': 'WFS',
        'version': '2.0.0',
        'request': 'GetFeature',
        'typeNames': kcslayer,
        'outputFormat': 'application/json',
        'CQL_FILTER': f"Intersects(geom, SRID={kcs_crs};{wkt_representation})"
    }

    try:
        kcs_response = requests.get(geoserver_url, params=kcs_params)
        kcs_data = kcs_response.json()
        logging.info(f'!--- filtering vector data: {kcslayer} filtered by filtergdf')
    except GeoserverException as ge:
        logging.error(f'! -- filtering vector data failed with Geoserverexception {ge}')
    except Exception as e:
        logging.error(f'! -- filtering vector data with nuts_gdf failed with {e}')
    
    # Create a GeoDataFrame from the roads data
    kcs_gdf = gpd.GeoDataFrame.from_features(kcs_data['features'], crs=CRS.from_epsg(4326))
    logging.info('!--- filtering vector data: {kcslayer} filtered by filtergdf')
    return kcs_gdf
