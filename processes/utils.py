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
import json
import configparser
import yaml

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
	if not os.path.isfile(fn):
		fn = os.path.join(os.path.dirname(os.path.abspath(__file__)),'app.yml')
		if not os.path.isfile(fn):
			print('no app.yml found')
		else:
			print(fn)
			with open(fn, "r") as f:
				return yaml.safe_load(f)
	else:
		with open(fn, "r") as f:
			return yaml.safe_load(f)