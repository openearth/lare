import logging

from pygeoapi.process.base import BaseProcessor, ProcessorExecuteError

from processes.lare_uomkcs import mainhandler_uomkcs

LOGGER = logging.getLogger(__name__)

PROCESS_METADATA = {
    'version': '1.0.0',
    'id': 'lare-uomkcs',
    'title': 'Key Community System aggregation',
    'description': (
        'Clips a key community system (KCS) layer, aggregates it to '
        'hexagons, overlays hazard data, and publishes the result.'
    ),
    'jobControlOptions': ['sync-execute', 'async-execute'],
    'inputs': {
        'sessionid': {
            'title': 'Session ID',
            'description': 'Unique session identifier from lare-start.',
            'schema': {'type': 'string'},
            'minOccurs': 1,
        },
        'kcs': {
            'title': 'Key Community System',
            'description': 'Name of the KCS layer to process (e.g. transport, pop2020).',
            'schema': {'type': 'string'},
            'minOccurs': 1,
        },
        'hazard': {
            'title': 'Hazard layer',
            'description': 'Hazard layer key from app config (e.g. pluvial_RP100).',
            'schema': {'type': 'string'},
            'minOccurs': 1,
        },
        'archetype': {
            'title': 'Archetype',
            'description': 'Archetype identifier (e.g. coastal).',
            'schema': {'type': 'string'},
            'minOccurs': 1,
        },
    },
    'outputs': {
        'result': {
            'title': 'KCS aggregation result',
            'schema': {'type': 'object', 'contentMediaType': 'application/json'},
        }
    },
}


class LareUomKcsProcessor(BaseProcessor):

    def __init__(self, processor_def):
        super().__init__(processor_def, PROCESS_METADATA)

    def execute(self, data):
        for key in ('sessionid', 'kcs', 'hazard', 'archetype'):
            if key not in data:
                raise ProcessorExecuteError(f'Missing required input: {key}')

        result = mainhandler_uomkcs(
            data['sessionid'],
            data['kcs'],
            data['hazard'],
            data['archetype'],
        )
        return 'application/json', result

    def __repr__(self):
        return '<LareUomKcsProcessor>'
