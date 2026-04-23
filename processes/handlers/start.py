# Copyright (C) 2025 Deltares
# SPDX-License-Identifier: GPL-3.0-or-later

import time
import logging
from pathlib import Path

from processes.config import get_config

logger = logging.getLogger(__name__)


def main_handler() -> dict:
    cfg = get_config()

    session_id = str(time.time()).replace('.', '')
    session_dir = Path(cfg.tmpdir) / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    logger.info('Session directory created: %s', session_dir)

    return {"session_id": session_id}
