# -*- coding: utf-8 -*-
# Copyright notice
#   --------------------------------------------------------------------
#   Copyright (C) 2018-2019 Deltares
#       Joan Sala
#       joan.salacalero@deltares.nl
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

# $HeadURL: https://svn.oss.deltares.nl/repos/openearthtools/trunk/python/applications/wps/ri2de/processes/utils.py $
# $Keywords: $

import time
import os
import pathlib
import shutil
import numpy as np
import json
import pandas as pd
import configparser
import yaml
import logging

logging.basicConfig(level=logging.INFO)

# Get a unique temporary file
def tempfile(tempdir, typen, extension):
    fname = typen + str(time.time()).replace('.','')
    return os.path.join(tempdir, fname+extension)

# Read default configuration from file
def read_config():
	# Default config file (relative path, does not work on production, weird)
	confpath = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'ri2de_configuration.txt')
	if not os.path.exists(confpath):	
		confpath = '/opt/pywps/processes/configuration.txt'
	# Parse and load
	cf = configparser.ConfigParser() 
	cf.read(confpath)
	return cf

# Read input [common parameters]
def read_input(request):
	layers_jsonstr = request.inputs["layers_setup"][0].data		
	layer_info = json.loads(layers_jsonstr)
	roads_id = request.inputs["roads_identifier"][0].data.strip()
	return layers_jsonstr, layer_info, roads_id

# Read input [common parameters]
def read_input_segments(request):
	buffer_dist = float(request.inputs["buffer_dist"][0].data)
	segment_length = float(request.inputs["segment_length"][0].data)
	return buffer_dist, segment_length

# Write output
def write_output(cf, wmslayer, defstyle='ri2de'):
	res = dict()
	res['baseUrl'] = cf.get('GeoServer', 'wms_url')
	res['layerName'] = wmslayer
	res['style'] = defstyle
	return json.dumps(res)
	
# Read default configuration from file
def read_setup():
	# Default layers file (relative path, does not work on production, weird)
	confpath = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'ri2de_layers.json')
	if not os.path.exists(confpath):	
		confpath = '/opt/pywps/processes/ri2de_layers.json'
	return confpath

# Read default susceptibilities configuration file
def read_susceptibilities():
	# Default layers file (relative path, does not work on production, weird)
	confpath = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'ri2de_susceptibilities.json')
	if not os.path.exists(confpath):	
		confpath = '/opt/pywps/processes/ri2de_susceptibilities.json'
	return confpath

def read_appyml(fn='app.yml'):
	"""Deprecated — use ``from processes.config import get_config`` instead."""
	import warnings
	warnings.warn(
		"read_appyml() is deprecated, use get_config() from processes.config",
		DeprecationWarning,
		stacklevel=2,
	)
	if not os.path.isfile(fn):
		fn = os.path.join(os.path.dirname(os.path.abspath(__file__)),'app.yml')
		if not os.path.isfile(fn):
			logging.info('!-- read_appyml - no app.yml found')
			return None
		else:
			logging.info(f'!-- read_appyml - {fn} found')
			with open(fn, "r") as f:
				return yaml.safe_load(f)
	else:
		with open(fn, "r") as f:
			return yaml.safe_load(f)
		
# -----------------------------
# 3. Load reclassification table
# -----------------------------
def load_reclass_table(csv_path, lusecol=None, reclasscol=None):
	if not os.path.isfile(csv_path):
		logging.error(f'File {csv_path} not found')
		return None
	try:
		df = pd.read_csv(csv_path, delimiter=';')
		logging.info(f'!-- lut loading successful, {csv_path}')
	except Exception as e:
		logging.error(f'Failed to read reclassification CSV {csv_path}:', e)
		return None
	if lusecol not in df.columns or reclasscol not in df.columns:
		logging.error(f'Columns "{lusecol}" and/or "{reclasscol}" not found in {csv_path}')
		return None
	return dict(zip(df[lusecol], df[reclasscol]))

def load_reclass_topo(csv_scores):
    csvpath = os.path.normpath(os.path.join(os.path.dirname( __file__ ), '..', csv_scores))
    df = pd.read_csv(csvpath,delimiter=';')
    return df

# -----------------------------
# 3. Load reclassification table 
#    with classes, to remap continuos data
# -----------------------------
def load_reclass_table_continousdata(csv_path,clmin='min',clmax='max',clscore='score'):
	print('load_reclass_table_continousdata ', csv_path)
	df = pd.read_csv(csv_path, sep=';')
    # Ensure numeric types
	df[clmin] = pd.to_numeric(df[clmin])
	df[clmax] = pd.to_numeric(df[clmax])
	df[clscore] = pd.to_numeric(df[clscore], downcast='integer')
	return df


def coerce_reclass_dict_to_array_dtype(array, reclass_dict):
	arr_type = array.dtype.type
	coerced = {}
	for k, v in reclass_dict.items():
		try:
			coerced[arr_type(k)] = v
		except Exception:
			coerced[k] = v
	return coerced


# ---- NODATA: compute nodata_cast AFTER dt is known ----
def compute_nodata_cast(src_nodata, target_dt):
	"""Return nodata cast to target dtype, or None if source had no nodata.
		Raise if NaN cannot be represented in integer target."""
	if src_nodata is None:
		return None

	target_dt = np.dtype(target_dt)

	# Floating targets can always carry NaN
	if np.issubdtype(target_dt, np.floating):
		# treat any NaN-like nodata as NaN
		if isinstance(src_nodata, float) and np.isnan(src_nodata):
			return np.nan
		return target_dt.type(src_nodata)

	# Integer targets cannot represent NaN
	if isinstance(src_nodata, float) and np.isnan(src_nodata):
		raise ValueError(
			f"Source nodata is NaN but target dtype {target_dt} is integer. "
			"Choose an explicit integer nodata or keep a float dtype."
		)

	# Ensure integer nodata fits in the target integer range
	info = np.iinfo(target_dt)
	if not (info.min <= src_nodata <= info.max):
		raise ValueError(
			f"Source nodata {src_nodata} out of range for target dtype {target_dt} "
			f"[{info.min}, {info.max}]"
		)
	return target_dt.type(src_nodata)

def cleanup_pywps_tmp(tmp_dir):
	"""Cleans data from temporary directory

	Args:
		tmp_dir (string): path to temporary directory
	"""
	if not os.path.exists(tmp_dir):
		print(f"PyWPS tmp directory not found: {tmp_dir}")
		return

	print(f"\n▶ Cleaning up PyWPS temporary files in: {tmp_dir}")
	for entry in os.listdir(tmp_dir):
		path = os.path.join(tmp_dir, entry)
		try:
			if os.path.isfile(path) or os.path.islink(path):
				os.remove(path)
				print(f"  Deleted file: {entry}")
			elif os.path.isdir(path):
				shutil.rmtree(path)
				print(f"  Deleted directory: {entry}")
		except Exception as e:
			print(f"  Failed to delete {entry}: {e}")