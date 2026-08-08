# Copyright (C) 2025 Deltares
# SPDX-License-Identifier: GPL-3.0-or-later

import logging

from pydantic import ValidationError
from pygeoapi.process.base import BaseProcessor, ProcessorExecuteError

from processes.handlers.nbs import main_handler
from processes.models import NbsInputs

LOGGER = logging.getLogger(__name__)

PROCESS_METADATA = {
    'version': '1.0.0',
    'id': 'lare-nbs',
    'title': 'Get NBS per UOM',
    'description': (
        'Computes a per-hexagon Corine Land Cover (CLC) zonal histogram for '
        'urban, rural, or coastal Units of Measurement and republishes the '
        'GeoPackage with one count column per CLC class (clc_1 … clc_N) plus '
        'clc_majority (most frequent CLC class per hexagon).'
    ),
    'jobControlOptions': ['sync-execute', 'async-execute'],
    'inputs': {
        'session_id': {
            'title': 'Session ID',
            'description': 'Unique session identifier from lare-start.',
            'schema': {'type': 'string'},
            'minOccurs': 1,
        },
        'archetype': {
            'title': 'Archetype',
            'description': 'Landscape archetype used when creating the UoM (urban, rural, or coastal).',
            'schema': {'type': 'string', 'enum': ['urban', 'rural', 'coastal']},
            'minOccurs': 1,
        },
    },
    'outputs': {
        'result': {
            'title': 'NBS per UOM result',
            'schema': {'type': 'object', 'contentMediaType': 'application/json'},
        }
    },
    'example': {
        'inputs': {
            'session_id': '17751340029381046',
            'archetype': 'urban',
        }
    },
}


class LareNbsProcessor(BaseProcessor):

    def __init__(self, processor_def):
        super().__init__(processor_def, PROCESS_METADATA)

    def execute(self, data):
        try:
            inputs = NbsInputs.model_validate(data)
        except ValidationError as exc:
            raise ProcessorExecuteError(exc.errors()[0]['msg']) from exc

        try:
            result = main_handler(inputs.session_id, inputs.archetype)
        except FileNotFoundError as exc:
            raise ProcessorExecuteError(str(exc)) from exc
        except Exception as exc:
            raise ProcessorExecuteError(str(exc)) from exc

        return 'application/json', result

    def __repr__(self):
        return '<LareNbsProcessor>'
