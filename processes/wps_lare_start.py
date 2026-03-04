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
# http://localhost:5000/wps?service=wps&request=Execute&version=2.0.0&Identifier=lare_start
# 
# https://lare.openearth.eu/wps?service=wps&request=GetCapabilities&version=2.0.0
# https://lare.openearth.eu/wps?service=wps&request=Execute&version=2.0.0&Identifier=lare_start


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
from pywps.inout.outputs import ComplexOutput
from pywps.app.Common import Metadata

# local
from processes.lare_start import mainhandler

class WpsStart(Process):

	def __init__(self):
		# Input [in json format ]
		inputs = []

		# Output [in json format]
		outputs = [ComplexOutput('output_json',
		                         'LARE Start sesstion',
		                         supported_formats=[Format('application/json')])]

		super(WpsStart, self).__init__(
		    self._handler,
		    identifier='lare_start',
		    version='1.0',
		    title='LARE Start Process',
		    abstract='This process initializes a LARE session and provides a session ID.',
		    profile='',
		    metadata=[Metadata('WpsStart'), Metadata('wps/start')],
		    inputs=inputs,
		    outputs=outputs,
		    store_supported=False,
		    status_supported=False
		)


	def _handler(self, request, response):
		logging.info(f'!-- wps lare before try')
		try:		
	
			logging.info(f'!-- wps lare start session ID generation')

			#for now only a message is provided, this should be a list of layers to be loaded
			res = mainhandler()
			response.outputs['output_json'].data = res
		except Exception as e:
			res = { 'errMsg' : 'ERROR: {}'.format(e) }
			logging.info(f'!-- wps lare {res}')
			response.outputs['output_json'].data = json.dumps(res)
		return response
