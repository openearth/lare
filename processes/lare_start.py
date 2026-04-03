# -*- coding: utf-8 -*-
# Copyright notice
#   --------------------------------------------------------------------
#   Copyright (C) 2025 Deltares
#       Ioanna Micha, Gerrit Hendriksen
#       ioanna.micha@deltares.nl, gerrit.hendriksen@deltares.nl
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

import time
import logging
from pathlib import Path

from processes.config import get_config

logger = logging.getLogger(__name__)


def mainhandler() -> dict:
    cfg = get_config()

    sessionid = str(time.time()).replace('.', '')
    sessiondir = Path(cfg.tmpdir) / sessionid
    sessiondir.mkdir(parents=True, exist_ok=True)
    logger.info('Session directory created: %s', sessiondir)

    return {"sessionid": sessionid}
