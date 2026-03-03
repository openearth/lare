# -*- coding: utf-8 -*-
# Copyright notice
#   --------------------------------------------------------------------
#   Copyright (C) 2025 Deltares
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

# native
import os
import json
import random
import yaml
import time
import logging

# local
from processes.utils import read_appyml, tempfile

def mainhandler():
        
    msg = None

    # check if hazard provided is listed in the list of hazards
    appconfig = read_appyml('app.yml')    
    tmpdir = appconfig['sdi']['tmp']['tmpdir']

    #create unique id that acts as sessionid
    sessionid = str(time.time()).replace('.','')
        
    sessiondir = os.path.join(tmpdir, str(sessionid))
    if not os.path.exists(sessiondir):
        os.makedirs(sessiondir)
        logging.info(f'-- Session directory created: {sessiondir}')

    try:
        merged = {"sessionid": sessionid}
        return json.dumps(merged, indent=2)
    except Exception as e:
        return json.dumps(msg)