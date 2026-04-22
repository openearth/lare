FROM geopython/pygeoapi:latest

COPY pyproject.toml /pygeoapi/
COPY processes/ /pygeoapi/processes/

# Install project with dev extras (includes debugpy for attach debugging)
RUN cd /pygeoapi && /venv/bin/pip install --no-cache-dir ".[dev]"

COPY app.yml /pygeoapi/app.yml
