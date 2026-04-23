# Copyright (C) 2025 Deltares
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
import shutil
from pathlib import Path

from processes.config import get_config

logger = logging.getLogger(__name__)


def mainhandler_reset(session_id: str) -> dict:
    cfg = get_config()

    session_dir = Path(cfg.tmpdir) / session_id

    if not session_dir.exists():
        raise FileNotFoundError(
            f'Session directory for {session_id!r} does not exist.'
        )

    # Guard against path traversal – resolved path must be inside tmpdir
    if not session_dir.resolve().is_relative_to(Path(cfg.tmpdir).resolve()):
        raise ValueError('Invalid session ID.')

    shutil.rmtree(session_dir)
    logger.info('Session directory removed: %s', session_dir)

    return {"session_id": session_id, "status": "removed"}
