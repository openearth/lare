# Copyright (C) 2025 Deltares
# SPDX-License-Identifier: GPL-3.0-or-later

import time
import logging
from pathlib import Path

from processes.config import get_config

logger = logging.getLogger(__name__)


def mainhandler() -> dict:
    cfg = get_config()

    sessionid = str(time.time()).replace('.', '')
    sessiondir = Path(cfg.tmpdir) / sessionid
    logger.info('Session directory: %s', sessiondir)
    sessiondir.mkdir(parents=True, exist_ok=True)
    logger.info('Session directory created: %s', sessiondir)

    return {"sessionid": sessionid}
