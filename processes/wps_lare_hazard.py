# -*- coding: utf-8 -*-
# Copyright notice
#   --------------------------------------------------------------------
#   Copyright (C) 2019 Deltares
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
# http://localhost:5000/wps?service=wps&request=Execute&version=2.0.0&Identifier=lare_hazard&datainputs=nutsname=Menorca;hazard=fire
# http://localhost:5000/wps?service=wps&request=Execute&version=2.0.0&Identifier=lare_landscape&datainputs=nutsname={"nutsname":'Splitsko-dalmatinska županija'}

# other
import os
import json

# PyWPS
from pywps import Process, Format, FORMATS
from pywps.inout.inputs import LiteralInput
from pywps.inout.outputs import ComplexOutput
from pywps.app.Common import Metadata

# local
from .lare_landscape import mainhandler_hazard

class WpsLareHazard(Process):

	def __init__(self):
		# Input [in json format ]
		inputs = [
			LiteralInput(
                identifier='nutsname',
                title='Name of the level 3 nuts regions',
                abstract='String identifying the nutsregion, level 3',
                data_type='string',
                keywords=['nuts region', 'name', 'common name']
            ),
            LiteralInput(
                identifier='hazard',
                title='Name of the hazard',
                abstract='String identifying the hazard under consideration, should be one in the list of drought, erosion, fire, flood, heatwave.',
                data_type='string',
				keywords=['drought', 'erosion', 'fire', 'flood', 'heat']
            )]

		# Output [in json format]
		outputs = [ComplexOutput('output_json',
		                         'LARE hazard mitigation',
		                         supported_formats=[Format('application/json')])]

		super(WpsLareHazard, self).__init__(
		    self._handler,
		    identifier='lare_hazard',
		    version='1.0',
		    title='Characterise landscape based on biophysical data for a specified hazard',
		    abstract='This process calls creates datalayers, based on biophysical data, that identify the landscape. ' \
			         'The process is carried out for a selected region',
		    profile='',
		    metadata=[Metadata('WpsLareHazard'), Metadata('lare/hazard')],
		    inputs=inputs,
		    outputs=outputs,
		    store_supported=False,
		    status_supported=False
		)


	def _handler(self, request, response):

		try:		
			# call mainhandler
			nutsname = request.inputs.get('nutsname', [])[0].data
			hazard   = request.inputs.get('hazard', [])[0].data

			#for now only a message is provided, this should be a list of layers to be loaded
			message = mainhandler_hazard(nutsname, hazard)
			print(f'message {message}')
			data = json.load(message)
			response.outputs['output_json'].data = json.dumps(data, indent=4, sort_keys=True)

		except Exception as e:
			res = { 'errMsg' : 'ERROR: {}'.format(e) }
			response.outputs['output_json'].data = json.dumps(res)

		return response
