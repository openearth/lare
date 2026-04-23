# Copyright (C) 2025 Deltares
# SPDX-License-Identifier: GPL-3.0-or-later

import logging

from pygeoapi.process.base import BaseProcessor

from processes.handlers.start import mainhandler

LOGGER = logging.getLogger(__name__)

PROCESS_METADATA = {
    'version': '1.0.0',
    'id': 'lare-start',
    'title': 'Start LARE session',
    'description': 'Creates a new session directory and returns a unique session ID.',
    'jobControlOptions': ['sync-execute'],
    'inputs': {},
    'outputs': {
        'result': {
            'title': 'Session info',
            'schema': {'type': 'object', 'contentMediaType': 'application/json'},
        }
    },
    'example': {
        'inputs': {}
    },
}


class LareStartProcessor(BaseProcessor):

    def __init__(self, processor_def):
        super().__init__(processor_def, PROCESS_METADATA)

    def execute(self, data):
        result = mainhandler()
        return 'application/json', result

    def __repr__(self):
        return '<LareStartProcessor>'
