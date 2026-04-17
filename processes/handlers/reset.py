# Copyright (C) 2025 Deltares
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
import shutil
from pathlib import Path

from processes.config import get_config

logger = logging.getLogger(__name__)


def mainhandler_reset(sessionid: str) -> dict:
    cfg = get_config()

    sessiondir = Path(cfg.tmpdir) / sessionid

    if not sessiondir.exists():
        raise FileNotFoundError(
            f'Session directory for {sessionid!r} does not exist.'
        )

    # Guard against path traversal – resolved path must be inside tmpdir
    if not sessiondir.resolve().is_relative_to(Path(cfg.tmpdir).resolve()):
        raise ValueError('Invalid session ID.')

    shutil.rmtree(sessiondir)
    logger.info('Session directory removed: %s', sessiondir)

    return {"sessionid": sessionid, "status": "removed"}
