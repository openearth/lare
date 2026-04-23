# Copyright (C) 2025 Deltares
# SPDX-License-Identifier: GPL-3.0-or-later

import logging

from pydantic import ValidationError
from pygeoapi.process.base import BaseProcessor, ProcessorExecuteError

from processes.handlers.uom import main_handler
from processes.models import UomInputs

LOGGER = logging.getLogger(__name__)

PROCESS_METADATA = {
    'version': '1.0.0',
    'id': 'lare-uom',
    'title': 'Create Unit of Measurement layer',
    'description': (
        'Creates a hexagonal grid for a selected region and publishes '
        'it to GeoServer as the unit-of-measurement layer.'
    ),
    'jobControlOptions': ['sync-execute', 'async-execute'],
    'inputs': {
        'session_id': {
            'title': 'Session ID',
            'description': 'Unique session identifier from lare-start.',
            'schema': {'type': 'string'},
            'minOccurs': 1,
        },
        'uom_size': {
            'title': 'Hexagon size (m²)',
            'description': 'Target area of each hexagon in square metres.',
            'schema': {'type': 'integer'},
            'minOccurs': 1,
        },
        'layer_name': {
            'title': 'Layer name',
            'description': 'Full workspace:layer_name from the data service.',
            'schema': {'type': 'string'},
            'minOccurs': 1,
        },
        'id': {
            'title': 'Feature ID',
            'description': 'ID or name of the region/basin feature to select.',
            'schema': {'type': 'string'},
            'minOccurs': 1,
        },
        'archetype': {
            'title': 'Archetype',
            'description': 'Archetype identifier (e.g. coastal, urban, rural).',
            'schema': {'type': 'string'},
            'minOccurs': 1,
        },
    },
    'outputs': {
        'result': {
            'title': 'Published layer info',
            'schema': {'type': 'object', 'contentMediaType': 'application/json'},
        }
    },
    'example': {
        'inputs': {
            'session_id': '17751340029381046',
            'uom_size': 100000,
            'layer_name': 'region:nuts_2021',
            'id': 'Cantabria',
            'archetype': 'coastal',
        }
    },
}


class LareUomProcessor(BaseProcessor):

    def __init__(self, processor_def):
        super().__init__(processor_def, PROCESS_METADATA)

    def execute(self, data):
        try:
            inputs = UomInputs.model_validate(data)
        except ValidationError as exc:
            raise ProcessorExecuteError(exc.errors()[0]['msg']) from exc

        try:
            result = main_handler(
                inputs.session_id,
                inputs.uom_size,
                inputs.layer_name,
                inputs.id,
                inputs.archetype,
            )
        except (FileNotFoundError, ValueError) as exc:
            raise ProcessorExecuteError(str(exc)) from exc
        return 'application/json', result

    def __repr__(self):
        return '<LareUomProcessor>'
