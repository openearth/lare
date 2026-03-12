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
# http://localhost:5000/wps?service=wps&request=Execute&version=2.0.0&Identifier=lare_kcs&datainputs=sessionid=17727241142485569;kcs=transport;hazard=pluvial_RP200
#  
# https://lare.openearth.eu/wps?service=wps&request=GetCapabilities&version=2.0.0
# https://lare.openearth.eu/wps?service=wps&request=Execute&version=2.0.0&lare_kcs&datainputs=sessionid=1772550772282953;kcs=transport;hazard=fire_17701219335645576

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
from .lare_uomkcs import mainhandler_uomkcs

class WpsLareKCS(Process):

	def __init__(self):
		# Input [in json format ]
		inputs = [
			LiteralInput(
                identifier='sessionid',
                title='Session ID',
                abstract='String identifying the session ID of the LARE process',
                data_type='string',
                keywords=['session', 'identifier']
            ),
			LiteralInput(
                identifier='kcs',
                title='Key Community System of preference',
                abstract='String identifying the Key Community System',
                data_type='string',
                keywords=['KCS', 'Key Community System', 'population','schools','elderlyhomes', 'hospitals','roads']
            ),
			LiteralInput(
                identifier='hazard',
                title='Hazard layer identifier',
                abstract='Name of the hazard layer created in previous step',
                data_type='string',
				keywords=['hazard','layername']
            )]

		# Output [in json format]
		outputs = [ComplexOutput('uomkcs',
		                         'LARE UoM with attributes of kcs',
		                         supported_formats=[Format('application/json')])]

		super(WpsLareKCS, self).__init__(
		    self._handler,
		    identifier='lare_kcs',
		    version='1.0',
		    title='Updates Unit of Measurment layer with KCS',
		    abstract='This process updates datalayers of unit of measurement with KCS data (stats)' \
			         'The process is carried out for the selected region, hazard',
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
			kcs       = request.inputs.get('kcs', [])[0].data
			hazardlr  = request.inputs.get('hazard', [])[0].data
			logging.info(f'!-- wps lare hazard create uon for sessionid {sessionid}')
			logging.info(f'!-- wps lare hazard create uon for kcs {kcs}')

			#for now only a message is provided, this should be a list of layers to be loaded
			res = mainhandler_uomkcs(sessionid, kcs, hazardlr)
			response.outputs['uomkcs'].data = res
		except Exception as e:
			res = { 'errMsg' : 'ERROR: {}'.format(e) }
			logging.info(f'!-- wps lare {res}')
			response.outputs['uomkcs'].data = json.dumps(res)
		return response
