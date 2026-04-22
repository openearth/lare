# Copyright (C) 2025 Deltares
# SPDX-License-Identifier: GPL-3.0-or-later

import logging

from pydantic import ValidationError
from pygeoapi.process.base import BaseProcessor, ProcessorExecuteError

from processes.handlers.reset import mainhandler_reset
from processes.models import ResetInputs

LOGGER = logging.getLogger(__name__)

PROCESS_METADATA = {
    'version': '1.0.0',
    'id': 'lare-reset',
    'title': 'Reset LARE session',
    'description': (
        'Removes the temporary working directory for a given session, '
        'allowing the user to start over.'
    ),
    'jobControlOptions': ['sync-execute'],
    'inputs': {
        'session_id': {
            'title': 'Session ID',
            'description': 'Unique session identifier from lare-start.',
            'schema': {'type': 'string'},
            'minOccurs': 1,
        },
    },
    'outputs': {
        'result': {
            'title': 'Reset result',
            'schema': {'type': 'object', 'contentMediaType': 'application/json'},
        },
    },
    'example': {
        'inputs': {
            'session_id': '17751340029381046',
        }
    },
}


class LareResetProcessor(BaseProcessor):

    def __init__(self, processor_def):
        super().__init__(processor_def, PROCESS_METADATA)

    def execute(self, data):
        try:
            inputs = ResetInputs.model_validate(data)
        except ValidationError as exc:
            raise ProcessorExecuteError(exc.errors()[0]['msg']) from exc

        try:
            result = mainhandler_reset(inputs.session_id)
        except FileNotFoundError as exc:
            raise ProcessorExecuteError(str(exc)) from exc
        except Exception as exc:
            raise ProcessorExecuteError(str(exc)) from exc

        return 'application/json', result

    def __repr__(self):
        return '<LareResetProcessor>'
