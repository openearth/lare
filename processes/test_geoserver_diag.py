#!/usr/bin/env python
# Copyright (C) 2025 Deltares
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Diagnostic script to test GeoServer and environment
Run this on the deployment server to check versions and capabilities
"""

import sys
import os
import requests
from requests.auth import HTTPBasicAuth
import json

def test_geoserver_info(url, username, password):
    """Test GeoServer connection and get version info"""
    print("\n=== Testing GeoServer Connection ===")
    try:
        # Get GeoServer version
        r = requests.get(f"{url}/rest/about/version.json", 
                        auth=HTTPBasicAuth(username, password), 
                        timeout=10)
        if r.status_code == 200:
            print(f"✓ GeoServer connected successfully")
            print(f"Version info: {json.dumps(r.json(), indent=2)}")
        else:
            print(f"✗ Failed to get version: {r.status_code}")
            print(f"Response: {r.text}")
    except Exception as e:
        print(f"✗ Connection failed: {e}")

def test_datastore_options(url, username, password):
    """Check datastore format support"""
    print("\n=== Testing Datastore Format Support ===")
    try:
        r = requests.get(f"{url}/rest/workspaces/tmp/datastores.json",
                        auth=HTTPBasicAuth(username, password),
                        timeout=10)
        if r.status_code == 200:
            print(f"✓ Can access datastores in 'tmp' workspace")
        else:
            print(f"Status: {r.status_code}")
    except Exception as e:
        print(f"✗ Error: {e}")

def test_python_packages():
    """Test installed Python packages"""
    print("\n=== Testing Python Packages ===")
    
    packages = {
        'geopandas': 'geopandas',
        'fiona': 'fiona',
        'pyogrio': 'pyogrio',
        'requests': 'requests',
        'shapely': 'shapely',
        'pandas': 'pandas',
        'numpy': 'numpy',
    }
    
    for name, import_name in packages.items():
        try:
            mod = __import__(import_name)
            version = getattr(mod, '__version__', 'unknown')
            print(f"✓ {name}: {version}")
        except ImportError as e:
            print(f"✗ {name}: NOT INSTALLED - {e}")
    
    # Special test for geopandas functionality
    print("\n--- Testing GeoPandas Functionality ---")
    try:
        import geopandas as gpd
        from shapely.geometry import Point
        # Create a simple GeoDataFrame
        gdf = gpd.GeoDataFrame(
            {'name': ['test']},
            geometry=[Point(0, 0)],
            crs='EPSG:4326'
        )
        print(f"✓ GeoPandas can create GeoDataFrame")
        print(f"✓ GeoDataFrame CRS: {gdf.crs}")
    except Exception as e:
        print(f"✗ GeoPandas functionality test failed: {e}")

def test_gdal():
    """Test GDAL/OGR installation"""
    print("\n=== Testing GDAL/OGR ===")
    try:
        from osgeo import gdal, ogr
        print(f"✓ GDAL version: {gdal.__version__}")
        
        # Check GPKG driver
        driver = ogr.GetDriverByName('GPKG')
        if driver:
            print(f"✓ GPKG driver available")
        else:
            print(f"✗ GPKG driver NOT available")
    except ImportError:
        print(f"✗ GDAL not installed")
    except Exception as e:
        print(f"✗ Error: {e}")

def test_file_permissions(dir_path):
    """Test file permissions"""
    print(f"\n=== Testing File Permissions: {dir_path} ===")
    try:
        if os.path.exists(dir_path):
            print(f"✓ Directory exists")
            # Try to create a test file
            test_file = os.path.join(dir_path, 'test_write.tmp')
            try:
                with open(test_file, 'w') as f:
                    f.write('test')
                print(f"✓ Can write to directory")
                os.remove(test_file)
                print(f"✓ Can delete from directory")
            except Exception as e:
                print(f"✗ Write/Delete failed: {e}")
        else:
            print(f"✗ Directory does not exist")
    except Exception as e:
        print(f"✗ Error: {e}")

def test_gpkg_upload_methods(url, username, password, test_gpkg_path):
    """Test different GPKG upload methods"""
    print(f"\n=== Testing GPKG Upload Methods ===")
    
    if not os.path.exists(test_gpkg_path):
        print(f"✗ Test GPKG not found: {test_gpkg_path}")
        return
    
    workspace = "tmp"
    store_name = "test_upload_diagnostic"
    
    # Test 1: Upload with configure=none
    print("\n--- Test 1: configure=none ---")
    try:
        endpoint = f"{url}/rest/workspaces/{workspace}/datastores/{store_name}/file.gpkg?configure=none&update=overwrite"
        with open(test_gpkg_path, "rb") as f:
            r = requests.put(endpoint, 
                           auth=HTTPBasicAuth(username, password),
                           headers={"Content-Type": "application/octet-stream"},
                           data=f, 
                           timeout=60)
        print(f"Status: {r.status_code}")
        if r.status_code in [200, 201]:
            print(f"✓ Upload successful with configure=none")
        else:
            print(f"✗ Upload failed: {r.text}")
    except Exception as e:
        print(f"✗ Error: {e}")
    
    # Test 2: Upload with configure=first
    print("\n--- Test 2: configure=first ---")
    store_name2 = "test_upload_diagnostic2"
    try:
        endpoint = f"{url}/rest/workspaces/{workspace}/datastores/{store_name2}/file.gpkg?configure=first&update=overwrite"
        with open(test_gpkg_path, "rb") as f:
            r = requests.put(endpoint,
                           auth=HTTPBasicAuth(username, password),
                           headers={"Content-Type": "application/octet-stream"},
                           data=f,
                           timeout=60)
        print(f"Status: {r.status_code}")
        if r.status_code in [200, 201]:
            print(f"✓ Upload successful with configure=first")
            
            # Check if layers were auto-configured
            import time
            time.sleep(2)
            r2 = requests.get(f"{url}/rest/workspaces/{workspace}/datastores/{store_name2}/featuretypes.json",
                            auth=HTTPBasicAuth(username, password),
                            timeout=30)
            print(f"Feature types response: {r2.json()}")
        else:
            print(f"✗ Upload failed: {r.text}")
    except Exception as e:
        print(f"✗ Error: {e}")

if __name__ == "__main__":
    # Configuration - EDIT THESE VALUES
    GEOSERVER_URL = "http://localhost:8080/geoserver"  # Change to your GeoServer URL
    USERNAME = "admin"  # Change to your username
    PASSWORD = "geoserver"  # Change to your password
    TMP_DIR = "/tmp"  # Change to your tmp directory
    TEST_GPKG = "/path/to/test.gpkg"  # Path to a test GPKG file
    
    print("=" * 60)
    print("GeoServer & Environment Diagnostic Tool")
    print("=" * 60)
    
    # Try to read from app.yml if available
    try:
        from processes.utils import read_appyml
        appconfig = read_appyml('app.yml')
        GEOSERVER_URL = appconfig['sdi']['geoserver']['url']
        USERNAME = appconfig['sdi']['geoserver']['user']
        PASSWORD = appconfig['sdi']['geoserver']['password']
        TMP_DIR = appconfig['sdi']['tmp']['tmpdir']
        print(f"\n✓ Loaded config from app.yml")
    except:
        print(f"\n! Using default configuration values - edit script to customize")
    
    print(f"\nGeoServer URL: {GEOSERVER_URL}")
    print(f"TMP Directory: {TMP_DIR}")
    
    # Run tests
    test_python_packages()
    test_gdal()
    test_geoserver_info(GEOSERVER_URL, USERNAME, PASSWORD)
    test_datastore_options(GEOSERVER_URL, USERNAME, PASSWORD)
    test_file_permissions(TMP_DIR)
    
    # Uncomment to test GPKG upload with a test file
    # test_gpkg_upload_methods(GEOSERVER_URL, USERNAME, PASSWORD, TEST_GPKG)
    
    print("\n" + "=" * 60)
    print("Diagnostic Complete")
    print("=" * 60)
