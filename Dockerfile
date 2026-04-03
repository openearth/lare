FROM geopython/pygeoapi:latest

COPY pyproject.toml /pygeoapi/
COPY processes/ /pygeoapi/processes/

# Install the project as a proper package (deps from pyproject.toml)
RUN cd /pygeoapi && /venv/bin/pip install --no-cache-dir .

COPY app.yml /pygeoapi/app.yml
