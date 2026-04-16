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
# http://localhost:5000/wps?service=wps&request=Execute&version=2.0.0&Identifier=lare_basin&datainputs=sessionid=1773324234723672;basinid=2121225160
# 
# https://lare.openearth.eu/wps?service=wps&request=GetCapabilities&version=2.0.0
# https://lare.openearth.eu/wps?service=wps&request=Execute&version=2.0.0&Identifier=lare_basin&datainputs=basinname='Rhine'

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
from .lare_basin import mainhandler_basin

class WpsLareBasin(Process):

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
                identifier='basinid',
                title='id of the basin',
                abstract='String identifying the basin, e.g. Rhine, Meuse, Scheldt, Ems, Elbe, Oder, Vistula',
                data_type='string',
                keywords=['basin', 'name', 'common name']
            )]

		# Output [in json format]
		outputs = [ComplexOutput(identifier='output_json',
						   		 title='Output json',
								 abstract='Output JSON with link to the Geoserver layer for the selected basin and the suggested unit of measurement size in m².',
		                         supported_formats=[Format('application/json')])]

		super(WpsLareBasin, self).__init__(
		    self._handler,
		    identifier='lare_basin',
		    version='1.0',
		    title='Select Basin',
		    abstract='This process enables selection of a basin and returns the suggested size of the unit of measurement in m2' \
			         'The process is carried out for a selected basin, and the output is a JSON with a link to the Geoserver layer for the selected basin and the suggested unit of measurement size in m².',
		    profile='',
		    metadata=[Metadata('WpsLareBasin'), Metadata('lare/basin')],
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
			basinid = request.inputs.get('basinid', [])[0].data
			logging.info(f'!-- wps lare basin, create dataframe basin_id {basinid} for session {sessionid}')

			# Single JSON output: layers + suggested_uom
			res = mainhandler_basin(sessionid, basinid)
			response.outputs['output_json'].data = res
		except Exception as e:
			res = {'errMsg': 'ERROR: {}'.format(e), 'suggested_uom': 0}
			logging.info(f'!-- wps lare {res}')
			response.outputs['output_json'].data = json.dumps(res)
		return response
