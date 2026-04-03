"""Demo OGC API - Processes plugin (see Dive Exercise 8).

At runtime the Docker image copies this file into ``pygeoapi/process/`` so the
processor is registered as ``pygeoapi.process.ultimate_question``.
"""

import logging

from pygeoapi.process.base import BaseProcessor

LOGGER = logging.getLogger(__name__)

PROCESS_METADATA = {
    'version': '1.0.0',
    'id': 'ultimate-question',
    'title': 'Answer to the Ultimate Question',
    'description': (
        'Returns the Answer to the Ultimate Question of Life, the Universe, '
        'and Everything.'
    ),
    'jobControlOptions': ['sync-execute'],
    'inputs': {
        'question': {
            'title': 'Your question',
            'description': 'Ask anything. The answer is always 42.',
            'schema': {'type': 'string'},
            'minOccurs': 0,
        },
    },
    'outputs': {
        'answer': {
            'title': 'The Answer',
            'schema': {'type': 'object', 'contentMediaType': 'application/json'},
        }
    },
}


class UltimateQuestionProcessor(BaseProcessor):

    def __init__(self, processor_def):
        super().__init__(processor_def, PROCESS_METADATA)

    def execute(self, data):
        question = data.get('question', 'What is the meaning of life?')
        LOGGER.info('Received question: %s', question)

        result = {
            'question': question,
            'answer': 42,
            'source': 'Deep Thought (7.5 million years of computation)',
        }
        return 'application/json', result

    def __repr__(self):
        return '<UltimateQuestionProcessor>'
