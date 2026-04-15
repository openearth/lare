import logging

from pygeoapi.process.base import BaseProcessor, ProcessorExecuteError

from processes.handlers.coastal import mainhandler_coastal

LOGGER = logging.getLogger(__name__)

PROCESS_METADATA = {
    'version': '1.0.0',
    'id': 'lare-coastal',
    'title': 'Coastal archetype analysis',
    'description': (
        'Identifies coastal zones, clips raster layers (CLC, DEM, imperviousness), '
        'aggregates data to the hexagonal grid, and publishes the result.'
    ),
    'jobControlOptions': ['sync-execute', 'async-execute'],
    'inputs': {
        'sessionid': {
            'title': 'Session ID',
            'description': 'Unique session identifier from lare-start.',
            'schema': {'type': 'string'},
            'minOccurs': 1,
        },
    },
    'outputs': {
        'result': {
            'title': 'Coastal analysis result',
            'schema': {'type': 'object', 'contentMediaType': 'application/json'},
        }
    },
}


class LareCoastalProcessor(BaseProcessor):

    def __init__(self, processor_def):
        super().__init__(processor_def, PROCESS_METADATA)

    def execute(self, data):
        sessionid = data.get('sessionid')
        if not sessionid:
            raise ProcessorExecuteError('Missing required input: sessionid')

        result = mainhandler_coastal(sessionid)
        return 'application/json', result

    def __repr__(self):
        return '<LareCoastalProcessor>'
