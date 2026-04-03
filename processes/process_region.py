import logging

from pygeoapi.process.base import BaseProcessor, ProcessorExecuteError

from processes.lare_region import mainhandler_region

LOGGER = logging.getLogger(__name__)

PROCESS_METADATA = {
    'version': '1.0.0',
    'id': 'lare-region',
    'title': 'Select LARE region',
    'description': (
        'Clips a region from WFS by name, publishes it to GeoServer, '
        'and returns a suggested unit-of-measurement size.'
    ),
    'jobControlOptions': ['sync-execute'],
    'inputs': {
        'name': {
            'title': 'Region name',
            'description': 'Name of the NUTS region or basin to select.',
            'schema': {'type': 'string'},
            'minOccurs': 1,
        },
    },
    'outputs': {
        'result': {
            'title': 'Region info with suggested UoM',
            'schema': {'type': 'object', 'contentMediaType': 'application/json'},
        }
    },
}


class LareRegionProcessor(BaseProcessor):

    def __init__(self, processor_def):
        super().__init__(processor_def, PROCESS_METADATA)

    def execute(self, data):
        name = data.get('name')
        if not name:
            raise ProcessorExecuteError('Missing required input: name')

        result = mainhandler_region(name)
        return 'application/json', result

    def __repr__(self):
        return '<LareRegionProcessor>'
