FROM geopython/pygeoapi:latest

# Install into pygeoapi's process package (Dive Exercise 8 pattern:
# pygeoapi.process.ultimate_question.UltimateQuestionProcessor)
COPY processes/ultimate_question.py /pygeoapi/pygeoapi/process/ultimate_question.py
