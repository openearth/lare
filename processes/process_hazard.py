import logging

from pygeoapi.process.base import BaseProcessor, ProcessorExecuteError

from processes.handlers.hazard import mainhandler_hazard

LOGGER = logging.getLogger(__name__)

PROCESS_METADATA = {
    'version': '1.0.0',
    'id': 'lare-hazard',
    'title': 'Hazard mitigation scoring',
    'description': (
        'For a given region and hazard type, clips CLC raster data, '
        'applies lookup-table scoring, and publishes the result.'
    ),
    'jobControlOptions': ['sync-execute', 'async-execute'],
    'inputs': {
        'name': {
            'title': 'Region name',
            'description': 'NUTS region name to process.',
            'schema': {'type': 'string'},
            'minOccurs': 1,
        },
        'hazard': {
            'title': 'Hazard type',
            'description': 'One of: flood, drought, erosion, heat, fire.',
            'schema': {'type': 'string', 'enum': ['flood', 'drought', 'erosion', 'heat', 'fire']},
            'minOccurs': 1,
        },
    },
    'outputs': {
        'result': {
            'title': 'Hazard scoring result',
            'schema': {'type': 'object', 'contentMediaType': 'application/json'},
        }
    },
}


class LareHazardProcessor(BaseProcessor):

    def __init__(self, processor_def):
        super().__init__(processor_def, PROCESS_METADATA)

    def execute(self, data):
        for key in ('name', 'hazard'):
            if key not in data:
                raise ProcessorExecuteError(f'Missing required input: {key}')

        result = mainhandler_hazard(data['name'], data['hazard'])
        return 'application/json', result

    def __repr__(self):
        return '<LareHazardProcessor>'
