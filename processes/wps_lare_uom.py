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

# example requests
# http://localhost:5000/wps?service=wps&request=GetCapabilities&version=2.0.0
# http://localhost:5000/wps?service=wps&request=Execute&version=2.0.0&Identifier=lare_uom&datainputs=nutsname='Menorca';uomsize=5000000
# http://localhost:5000/wps?service=wps&request=Execute&version=2.0.0&Identifier=lare_uom&datainputs=sessionid=1772550772282953;uomsize=100000;layername=hydro:hybas_eu_lev12_v1c;id=2120048760;
# http://localhost:5000/wps?service=wps&request=Execute&version=2.0.0&Identifier=lare_uom&datainputs=sessionid=1772550772282953;uomsize=100000;layername=region:nuts_2021;id=Menorca;
# 
# https://lare.openearth.eu/wps?service=wps&request=GetCapabilities&version=2.0.0
# https://lare.openearth.eu/wps?service=wps&request=Execute&version=2.0.0&Identifier=lare_uom&datainputs=sessionid=17726137987513835;uomsize=100000;layername=region:nuts_2021;id=Menorca
# https://lare.openearth.eu/wps?service=wps&request=Execute&version=2.0.0&Identifier=lare_uom&datainputs=sessionid=1772550772282953;uomsize=100000;layername=hydro:hybas_eu_lev12_v1c;id=2120048760;


# todo:
# - switch for hydrobasin or nuts region
# - as output add sessionid


# other
import os
import json
import logging

logging.basicConfig(level=logging.INFO)

# PyWPS
from pywps import Process, Format, FORMATS
from pywps.inout.inputs import LiteralInput
from pywps.inout.outputs import ComplexOutput
from pywps.app.Common import Metadata

# local
from .lare_uom import mainhandler_uom

class WpsLareUoM(Process):

	def __init__(self):
		# Input [in json format ]
		inputs = [
			LiteralInput(
                identifier='sessionid',
                title='Session ID',
                abstract='String identifying the LARE session',
                data_type='string',
                keywords=['session', 'identifier']
            ),
            LiteralInput(
                identifier='uomsize',
                title='Size of the hexagons in square meters',
                abstract='Integer size of the hexagon in square meters',
                data_type='integer',
				keywords=['uom','unit of measurement']
            ),
			LiteralInput(
				identifier='layername',
				title='layername ',
				abstract='String identifying the full workspace layername from a dataservice',
				data_type='string',
				keywords=['dataset', 'dataservice']
			),
			LiteralInput(
				identifier='id',
				title='id of the dataset, e.g. name of the region or basin',
				abstract='String identifying the dataset id, e.g. name of the region or basin',
				data_type='string',
				keywords=['dataset', 'id']
				)]

		# Output [in json format]
		outputs = [ComplexOutput('output_json',
		                         'LARE UoM creation',
		                         supported_formats=[Format('application/json')])]

		super(WpsLareUoM, self).__init__(
		    self._handler,
		    identifier='lare_uom',
		    version='1.0',
		    title='Create Unit of Measurment layer',
		    abstract='This process creates datalayers unit of measurement based on nutsname and area' \
			         'The process is carried out for a selected region',
		    profile='',
		    metadata=[Metadata('WpsLareUoM'), Metadata('lare/uom')],
		    inputs=inputs,
		    outputs=outputs,
		    store_supported=False,
		    status_supported=False
		)


	def _handler(self, request, response):
		logging.info(f'!-- wps lare before try')
		try:		
			# call mainhandler
			sessionid = request.inputs.get('sessionid', [])[0].data
			uomsize   = request.inputs.get('uomsize', [])[0].data
			layername   = request.inputs.get('layername',[])[0].data
			id        = request.inputs.get('id',[])[0].data
			logging.info(f'!-- wps lare hazard create uon for layername {layername} with size {str(uomsize)} for id {id}')

			#for now only a message is provided, this should be a list of layers to be loaded
			res = mainhandler_uom(sessionid, uomsize,layername,id)
			response.outputs['output_json'].data = res
		except Exception as e:
			res = { 'errMsg' : 'ERROR: {}'.format(e) }
			logging.info(f'!-- wps lare {res}')
			response.outputs['output_json'].data = json.dumps(res)
		return response
