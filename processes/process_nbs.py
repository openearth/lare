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
        'urban, rural, or coastal Units of Measurement, writes the top 5 CLC '
        'ranks with their NBS lists for the given hazard and archetype, and '
        'selects clc_nbs_majority / nbs_list_majority by searching all CLC '
        'classes with count > 0 (not limited to the displayed ranks). Writes '
        'clc_* counts, clc_majority, clc_rank_1..5, nbs_list_1..5, '
        'clc_nbs_majority, nbs_list_majority, and clc_nbs_majority_area (m2).'
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
        'hazard': {
            'title': 'Hazard',
            'description': (
                'Hazard key from app config (e.g. heat, drought, pluvial_RP200). '
                'Used to look up NBS options in clc_nbs_hazard.csv.'
            ),
            'schema': {'type': 'string'},
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
            'hazard': 'heat',
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
            result = main_handler(inputs.session_id, inputs.archetype, inputs.hazard)
        except FileNotFoundError as exc:
            raise ProcessorExecuteError(str(exc)) from exc
        except Exception as exc:
            raise ProcessorExecuteError(str(exc)) from exc

        return 'application/json', result

    def __repr__(self):
        return '<LareNbsProcessor>'
