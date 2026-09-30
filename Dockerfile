FROM geopython/pygeoapi:latest

COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock /pygeoapi/
COPY processes/ /pygeoapi/processes/

# Keep the base image's system-site-packages venv and its pygeoapi installation.
RUN UV_PROJECT_ENVIRONMENT=/venv uv sync --locked --inexact --extra dev --no-cache

COPY app.yml /pygeoapi/app.yml
