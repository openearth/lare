# Copyright (C) 2026 Deltares
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import json
import time
from pathlib import Path
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
from processes.config import get_config
from processes.utils.wfs import get_geometry_field

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

    cfg = get_config()

    # we might want to use styles
    dctstyles = {}
    dctstyles['fire']    = ("Fire mitigation",'fire')
    dctstyles['heat']    = ("Heatwave mitigation",'heat')
    dctstyles['drought']    = ("Drought mitigation",'drought')
    dctstyles['erosion']    = ("Erosion mitigation",'erosion')
    dctstyles['flood']    = ("Flood mitigation",'flood')

    try:
        geo = Geoserver(
            cfg.geoserver.resturl,
            username=cfg.geoserver.user,
            password=cfg.geoserver.password,
        )
    except Exception as e:
        logging.error('load2geoserver: cannot connect to GeoServer: %s', e)

    try:
        geo.get_workspaces()
        get_or_create_workspace(geo, aws)
    except GeoserverException as ge:
        logging.error('load2geoserver: workspace error: %s', ge)
    except Exception as e:
        logging.error('load2geoserver: workspace error: %s', e)

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
        except GeoserverException as ge:
            logging.error('load2geoserver: store/layer creation failed for %s: %s', lname, ge)
        except Exception as e:
            logging.error('load2geoserver: store/layer creation failed for %s: %s', lname, e)

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
    except (GeoserverException, Exception) as e:
        logging.error('cleanup_workspace_geoserver: could not connect: %s', e)
        return

    logging.info('cleanup_workspace_geoserver: GeoServer %s, cleaning workspace %s', geo.get_version(), workspace)

    # Try to get and delete layers
    try:
        layers = geo.get_layers(workspace=workspace)["layers"]
        if not layers:
            logging.info('cleanup_workspace_geoserver: no layers in workspace %r', workspace)
        else:
            for layer in layers["layer"]:
                lname = layer["name"]
                logging.info('cleanup_workspace_geoserver: deleting layer %s', lname)
                geo.delete_layer(layer_name=lname, workspace=workspace)
    except Exception as e:
        logging.error('cleanup_workspace_geoserver: failed to delete layers in %r: %s', workspace, e)

    # Try to get and delete coverage stores
    try:
        stores = geo.get_coveragestores(workspace=workspace)["coverageStores"]
        if not stores:
            logging.info('cleanup_workspace_geoserver: no coverage stores in workspace %r', workspace)
        else:
            for store in stores["coverageStore"]:
                store_name = store["name"]
                logging.info('cleanup_workspace_geoserver: deleting coverage store %s', store_name)
                geo.delete_coveragestore(coveragestore_name=store_name, workspace=workspace)
    except Exception as e:
        logging.error('cleanup_workspace_geoserver: failed to delete coverage stores in %r: %s', workspace, e)

def clean_geoserver():
    cfg = get_config()

    cleanup_workspace_geoserver(
        cfg.geoserver.url, cfg.geoserver.user, cfg.geoserver.password, 'tmp'
    )

    # TODO: call utils.clean_tmp for tif and xml files in cfg.tmpdir

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
                              geoserver_gpkg_path=None,
                              configure="none", update="overwrite"):
        """Create a GeoPackage-backed datastore via the REST API.

        Points GeoServer at the file on disk (no byte upload).
        The POST is synchronous — returns 200/201 on success.
        """
        if not os.path.isfile(gpkg_path):
            raise FileNotFoundError(gpkg_path)

        gpkg_abs_path = os.path.abspath(gpkg_path)
        gpkg_geoserver_path = geoserver_gpkg_path or gpkg_abs_path
        endpoint = f"{self.url}/rest/workspaces/{ws}/datastores"

        payload = {
            "dataStore": {
                "name": store,
                "type": "GeoPackage",
                "enabled": True,
                "connectionParameters": {
                    "entry": [
                        {"@key": "database", "$": gpkg_geoserver_path},
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
        logging.info(
            'Datastore %s created (container path: %s, geoserver path: %s)',
            store,
            gpkg_abs_path,
            gpkg_geoserver_path,
        )


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
        """Ensure a layer resource exists, creating it if GeoServer did not auto-create it."""
        r = requests.get(
            f"{self.url}/rest/workspaces/{ws}/layers/{layer_name}.json",
            auth=self.auth, timeout=self.timeout
        )
        if r.status_code == 200:
            return True
        if r.status_code not in (404,):
            logging.warning('ensure_layer_resource: unexpected status %s for %s', r.status_code, layer_name)

        # Option 1: simple payload (works in most GeoServer versions)
        try:
            r = requests.post(
                f"{self.url}/rest/workspaces/{ws}/layers",
                auth=self.auth, headers=self.h_json,
                data=json.dumps({"layer": {"name": layer_name}}), timeout=self.timeout
            )
            if r.status_code in (200, 201):
                return True
            logging.warning('ensure_layer_resource: simple payload → %s', r.status_code)
        except Exception as e:
            logging.warning('ensure_layer_resource: simple payload exception: %s', e)

        # Option 2: explicit resource reference
        try:
            r = requests.post(
                f"{self.url}/rest/workspaces/{ws}/layers",
                auth=self.auth, headers=self.h_json,
                data=json.dumps({"layer": {"name": layer_name, "resource": {"name": f"{ws}:{layer_name}"}}}),
                timeout=self.timeout
            )
            if r.status_code in (200, 201):
                return True
            logging.error('ensure_layer_resource: detailed payload → %s %s', r.status_code, r.text)
            return False
        except Exception as e:
            logging.error('ensure_layer_resource: detailed payload exception: %s', e)
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
        while time.time() - start_time < max_wait:
            r = requests.get(
                f"{self.url}/rest/workspaces/{ws}/layers/{layer_name}.json",
                auth=self.auth, timeout=self.timeout
            )
            if r.status_code == 200:
                return True
            if r.status_code != 404:
                logging.warning('layer_exists: unexpected status %s for %s', r.status_code, layer_name)
            time.sleep(1)

        logging.error("layer_exists: '%s' not available after %ss", layer_name, max_wait)
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
        
        style_ws = None
        if self.style_exists(style_name, ws=ws):
            style_ws = ws
        elif not self.style_exists(style_name):
            raise RuntimeError(f"Style '{style_name}' does not exist in workspace '{ws}' or global styles")

        if style_ws:
            payload = {"layer": {"defaultStyle": {"name": style_name, "workspace": style_ws}}}
        else:
            payload = {"layer": {"defaultStyle": {"name": style_name}}}

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

def _map_container_path_for_geoserver(gpkg_path: str, cfg) -> str:
    """Translate a container-local path to a GeoServer-host visible path.

    Mapping is controlled by optional env vars:
      - LARE_TMPDIR_CONTAINER (defaults to cfg.tmpdir)
      - LARE_TMPDIR_HOST
    """
    local_abs = os.path.abspath(gpkg_path)
    container_root = os.environ.get('LARE_TMPDIR_CONTAINER', cfg.tmpdir)
    host_root = os.environ.get('LARE_TMPDIR_HOST')

    if not host_root:
        return local_abs

    container_root_abs = os.path.abspath(container_root)
    try:
        rel = os.path.relpath(local_abs, container_root_abs)
    except ValueError:
        # Different drives / unrelated roots: fallback to local path.
        return local_abs

    if rel.startswith('..'):
        return local_abs

    return str(Path(host_root) / Path(rel))


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
    cfg = get_config()

    try:
        gs = GS(cfg.geoserver.resturl, cfg.geoserver.user, cfg.geoserver.password)
        gs.ensure_workspace(workspace)
        # Remove any stale layer/featureType from a previous run so the
        # subsequent publish is always idempotent.  Both helpers treat 404
        # as success, so a first-time run is unaffected.
        gs.delete_layer(workspace, layer_name)
        gs.delete_featuretype(workspace, store, layer_name)
        gs.publish_featuretype(
            ws=workspace,
            store=store,
            layer_name=layer_name,
            title=title,
            native_name=native_name or store,
        )
        gs.reload_catalog()
        if style_name:
            gs.set_default_style(
                ws=workspace,
                layer_name=layer_name,
                style_name=style_name,
                wait_for_layer=wait_for_layer,
                max_wait=max_wait,
                skip_verification=False,
            )
        logging.info("republish_layer: '%s' published with style '%s'", layer_name, style_name)
        return True
    except Exception as e:
        logging.error("republish_layer: failed for '%s': %s", layer_name, e)
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
    t0 = time.perf_counter()
    cfg = get_config()
    geoserver_url = cfg.geoserver.resturl
    username = cfg.geoserver.user
    password = cfg.geoserver.password
    lname = os.path.basename(gpkg_path).replace('.gpkg', '')
    datastore = datastore_name or lname

    t_connect_start = time.perf_counter()
    gs = GS(geoserver_url, username, password)
    gs.ensure_workspace(workspace)
    t_connect_end = time.perf_counter()

    geoserver_gpkg_path = _map_container_path_for_geoserver(gpkg_path, cfg)
    logging.info('publish_gpkg: datastore path mapping local=%s geoserver=%s', gpkg_path, geoserver_gpkg_path)

    t_datastore_start = time.perf_counter()
    gs.upload_gpkg_datastore(workspace, datastore, gpkg_path,
                             geoserver_gpkg_path=geoserver_gpkg_path,
                             configure="none", update="overwrite")
    t_datastore_end = time.perf_counter()

    # Poll for available feature types with exponential backoff
    available = []
    deadline = time.time() + scan_timeout
    sleep_s = 0.1
    t_scan_start = time.perf_counter()
    while time.time() < deadline:
        try:
            available = gs.list_available_featuretypes(workspace, datastore)
            if available:
                break
        except Exception:
            pass
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        time.sleep(min(sleep_s, remaining))
        sleep_s = min(sleep_s * 2, 5.0)
    t_scan_end = time.perf_counter()

    # Fallback: read layer names directly from the GPKG file
    if not available:
        import fiona
        available = fiona.listlayers(gpkg_path)
        logging.info('publish_gpkg: layers from GPKG file: %s', available)

    if not available:
        raise RuntimeError('No feature types found in GeoServer or GPKG file')

    published_layers = []
    publish_ft_seconds = 0.0
    style_seconds = 0.0
    for ft_name in available:
        ft_name = str(ft_name).strip()
        if not ft_name:
            continue

        publish_name = layer_name if (layer_name and len(available) == 1) else ft_name

        if republish:
            gs.delete_layer(workspace, publish_name)
            gs.delete_featuretype(workspace, datastore, publish_name)

        t_ft_start = time.perf_counter()
        gs.publish_featuretype(
            ws=workspace,
            store=datastore,
            layer_name=publish_name,
            native_name=ft_name if publish_name != ft_name else None,
        )
        publish_ft_seconds += time.perf_counter() - t_ft_start
        published_layers.append(publish_name)

        if style_name:
            try:
                t_style_start = time.perf_counter()
                gs.set_default_style(workspace, publish_name, style_name,
                                     wait_for_layer=True, max_wait=5,
                                     skip_verification=False)
                style_seconds += time.perf_counter() - t_style_start
            except Exception as exc:
                logging.warning('Style %s not set for %s: %s', style_name, publish_name, exc)

    t_end = time.perf_counter()
    logging.info(
        (
            'perf:publish_gpkg total_seconds=%.3f connect_seconds=%.3f '
            'upload_datastore_seconds=%.3f scan_featuretypes_seconds=%.3f '
            'publish_featuretype_seconds=%.3f set_style_seconds=%.3f '
            'published_count=%d datastore=%s'
        ),
        t_end - t0,
        t_connect_end - t_connect_start,
        t_datastore_end - t_datastore_start,
        t_scan_end - t_scan_start,
        publish_ft_seconds,
        style_seconds,
        len(published_layers),
        datastore,
    )
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


def publish_and_respond(gpkg_path: Path, folder: str, titles: dict) -> list[dict]:
    t0 = time.perf_counter()
    cfg = get_config()
    store_name = gpkg_path.stem
    gs = GS(cfg.geoserver.resturl, cfg.geoserver.user, cfg.geoserver.password)
    t_cleanup_start = time.perf_counter()
    try:
        gs.delete_layer_and_store('tmp', store_name)
    except Exception:
        pass
    t_cleanup_end = time.perf_counter()

    t_publish_start = time.perf_counter()
    wmslay = publish_gpkg(str(gpkg_path))
    t_publish_end = time.perf_counter()
    t_viewer_start = time.perf_counter()
    result = createvieweroutput(wmslay, folder, titles, cfg.geoserver.url)
    t_viewer_end = time.perf_counter()
    logging.info(
        (
            'perf:publish_and_respond total_seconds=%.3f cleanup_seconds=%.3f '
            'publish_gpkg_seconds=%.3f viewer_output_seconds=%.3f store=%s'
        ),
        t_viewer_end - t0,
        t_cleanup_end - t_cleanup_start,
        t_publish_end - t_publish_start,
        t_viewer_end - t_viewer_start,
        store_name,
    )
    return result


def filter_vector_by_vector(geoserver_url, filtergdf, filter_crs, kcslayer, kcs_crs):
    """Filter a vector layer on GeoServer by spatial intersection with a local GeoDataFrame geometry.

    Reprojects the filter geometry to the target CRS, converts it to WKT (simplifying
    large geometries to avoid oversized payloads), and issues a WFS GetFeature request
    with a CQL Intersects filter against the specified layer.

    Args:
        geoserver_url (str): Base WFS endpoint URL of the GeoServer instance.
        filtergdf (GeoDataFrame): GeoDataFrame whose first geometry is used as the
            spatial filter.
        filter_crs: CRS of *filtergdf* (used for documentation; the actual CRS is read
            from ``filtergdf.crs``).
        kcslayer (str): Fully-qualified GeoServer layer name to query
            (e.g. ``'workspace:layername'``).
        kcs_crs (int): EPSG code of the target layer's coordinate reference system.

    Returns:
        GeoDataFrame | None: A GeoDataFrame of intersecting features in the target CRS,
            an empty GeoDataFrame if no features match, or ``None`` on error.
    """
    try:
        if filtergdf is None or filtergdf.empty:
            logging.error('filter_vector_by_vector: filtergdf is None or empty')
            return None

        filter_epsg = filtergdf.crs.to_epsg() if filtergdf.crs else None
        #TODO: we need to change the name of nuts, because we support also the hydrobasins. 
        nuts_gdf = filtergdf.to_crs(epsg=kcs_crs) if filter_epsg != kcs_crs else filtergdf

        geom = nuts_gdf.geometry.iloc[0]
        if geom is None or geom.is_empty:
            logging.error('filter_vector_by_vector: geometry is None or empty')
            return None

        if not geom.is_valid:
            logging.warning('filter_vector_by_vector: invalid geometry, attempting buffer(0) fix')
            geom = geom.buffer(0)

        wkt_representation = dumps(geom, rounding_precision=6, trim=True)

        # Simplify very large geometries to avoid oversized WFS filter payloads.
        if len(wkt_representation) > 12000:
            minx, miny, maxx, maxy = geom.bounds
            span = max(maxx - minx, maxy - miny)
            tolerance = max(span * 0.0001, 1e-06)
            simplified_geom = geom.simplify(tolerance, preserve_topology=True)
            wkt_representation = dumps(simplified_geom, rounding_precision=6, trim=True)
            logging.info('filter_vector_by_vector: geometry simplified (tolerance=%s)', tolerance)

    except Exception as e:
        logging.error('filter_vector_by_vector: WKT preparation failed: %s', e)
        return None

    geom_field = get_geometry_field(geoserver_url, kcslayer)
    kcs_params = {
        'service': 'WFS',
        'version': '2.0.0',
        'request': 'GetFeature',
        'typeNames': kcslayer,
        'outputFormat': 'application/json',
        'CQL_FILTER': f"Intersects({geom_field}, SRID={kcs_crs};{wkt_representation})",
    }

    try:
        # Use POST to avoid "414 URI Too Long" for large polygon filters.
        kcs_response = requests.post(geoserver_url, data=kcs_params, timeout=120)

        # Fallback for servers that do not allow KVP POST.
        if kcs_response.status_code in (405, 501):
            logging.warning('filter_vector_by_vector: POST not supported (%s), falling back to GET', kcs_response.status_code)
            kcs_response = requests.get(geoserver_url, params=kcs_params, timeout=120)

        if kcs_response.status_code != 200:
            logging.error('filter_vector_by_vector: HTTP %s from %s', kcs_response.status_code, geoserver_url)
            return None

        try:
            kcs_data = kcs_response.json()
        except ValueError as ve:
            logging.error('filter_vector_by_vector: JSON parse failed: %s', ve)
            return None

        if 'features' not in kcs_data:
            logging.error('filter_vector_by_vector: no features key in response; keys=%s', list(kcs_data.keys()))
            return None

        logging.info('filter_vector_by_vector: %s → %d features', kcslayer, len(kcs_data['features']))

    except GeoserverException as ge:
        logging.error('filter_vector_by_vector: GeoserverException: %s', ge)
        return None
    except Exception as e:
        logging.error('filter_vector_by_vector: request failed: %s', e)
        return None

    try:
        if not kcs_data.get('features'):
            return gpd.GeoDataFrame()
        return gpd.GeoDataFrame.from_features(kcs_data['features'], crs=CRS.from_epsg(kcs_crs))
    except Exception as e:
        logging.error('filter_vector_by_vector: GeoDataFrame creation failed: %s', e)
        return None


def filtervectorbyvector(geoserver_url, filtergdf, filter_crs, kcslayer, kcs_crs):
    """Backward-compatible alias for ``filter_vector_by_vector``."""
    return filter_vector_by_vector(geoserver_url, filtergdf, filter_crs, kcslayer, kcs_crs)
