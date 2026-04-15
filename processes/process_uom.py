import logging

from pygeoapi.process.base import BaseProcessor, ProcessorExecuteError

from processes.handlers.uom import mainhandler_uom

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
        'sessionid': {
            'title': 'Session ID',
            'description': 'Unique session identifier from lare-start.',
            'schema': {'type': 'string'},
            'minOccurs': 1,
        },
        'uomsize': {
            'title': 'Hexagon size (m²)',
            'description': 'Target area of each hexagon in square metres.',
            'schema': {'type': 'integer'},
            'minOccurs': 1,
        },
        'layername': {
            'title': 'Layer name',
            'description': 'Full workspace:layername from the data service.',
            'schema': {'type': 'string'},
            'minOccurs': 1,
        },
        'id': {
            'title': 'Feature ID',
            'description': 'ID or name of the region/basin feature to select.',
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
            'sessionid': '17751340029381046',
            'uomsize': 100000,
            'layername': 'region:nuts_2021',
            'id': 'Cantabria',
        }
    },
}


class LareUomProcessor(BaseProcessor):

    def __init__(self, processor_def):
        super().__init__(processor_def, PROCESS_METADATA)

    def execute(self, data):
        for key in ('sessionid', 'uomsize', 'layername', 'id'):
            if key not in data:
                raise ProcessorExecuteError(f'Missing required input: {key}')

        try:
            result = mainhandler_uom(
                data['sessionid'],
                int(data['uomsize']),
                data['layername'],
                data['id'],
            )
        except (FileNotFoundError, ValueError) as exc:
            raise ProcessorExecuteError(str(exc)) from exc
        return 'application/json', result

    def __repr__(self):
        return '<LareUomProcessor>'
