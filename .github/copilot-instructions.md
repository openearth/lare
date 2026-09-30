# Copilot instructions for LARE

## Project scope

LARE (Landscape Resilience Explorer) is a Python 3.11+ OGC API Processes application deployed through [pygeoapi](https://pygeoapi.io/). It performs geospatial processing with GeoPandas/raster tooling, reads source layers from GeoServer, writes per-request artifacts under a session directory, and publishes result layers back to GeoServer.

## Build, run, and test

The supported development environment is Docker Compose. From the repository root:

```bash
docker compose up --build
```

The API is available at `http://localhost:5000`; useful endpoints are `/processes` and `/openapi`. The default Compose override mounts `processes/`, `app.yml`, and `tmp/` for live development and enables pygeoapi hot reload. Rebuild after changing dependencies in `pyproject.toml`:

```bash
docker compose build --no-cache
```

For production-style startup:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
```

For debugpy/IDE attach debugging:

```bash
docker compose -f docker-compose.yml -f docker-compose.debug.yml up --build
```

The project has no configured formatter, linter, or unit-test suite. `pytest` is included in the `dev` extra, and the diagnostic module can be run when its GeoServer/environment prerequisites are available:

```bash
python -m pytest diagnostics/test_geoserver_diag.py
python -m pytest diagnostics/test_geoserver_diag.py -k test_python_packages
```

The primary integration test is the saved API-case runner. Copy `tests/api_cases.example.json` to the ignored `tests/api_cases.local.json`, configure the cases and external datasets, then run:

```bash
python tests/run_api_tests.py --cases tests/api_cases.local.json
python tests/run_api_tests.py --mode async --cases tests/api_cases.local.json --timeout 180
```

To run one API case, provide a cases JSON file containing only that case; the runner has no case-name selector. Cases execute in order and may use `{{session_id}}` or `{{sessionid}}` placeholders populated from a prior `lare-start` response.

## Architecture

- `pygeoapi-config.yml` is the process registry. Each `resources` entry maps an API process ID to a `processes.process_*` processor class.
- `processes/process_*.py` contains thin pygeoapi `BaseProcessor` adapters. Keep `PROCESS_METADATA` synchronized with the input/output contract and delegate actual work to `processes/handlers/*.py`.
- `processes/models.py` contains Pydantic input models and validation, including config-backed validation for hazard names. Add or update the model when changing a process request contract.
- `processes/handlers/` contains the workflows for starting/resetting sessions, creating units of measure, aggregating KCS/hazard data, and selecting nature-based solutions. Shared geospatial and service integrations live under `processes/utils/` (`wfs`, `wcs`, raster/vector operations, sessions, and GeoServer publishing).
- `processes/config.py` loads `app.yml` once per process through the cached `get_config()` function. It exposes typed configuration plus convenience properties. Runtime `LARE_TMPDIR` overrides `sdi.tmp.tmpdir`; do not hardcode service URLs, layer names, credentials, data paths, or temporary paths in process code.
- A `lare-start` request creates a unique directory under the configured temp directory. Later processes use the session ID to read/write files such as `region.gpkg`, GeoPackages, and rasters. The Docker volume mapping must make this directory visible both to pygeoapi and to the external GeoServer configured in `app.yml`.
- GeoServer is an external dependency in the normal setup. Results are commonly written locally first and then registered/published through the shared GeoServer helpers. `LARE_TMPDIR_HOST` controls the host path sent to GeoServer when container and host paths differ.
- `data/` contains lookup tables and SLD styles used by the workflows; `lare-legacy/` contains the older pywps implementation and is not the registration path for the current pygeoapi service.

## Repository-specific conventions

- When adding a process, follow the documented sequence: define a Pydantic input model, implement a handler, add a `process_*.py` adapter and metadata, then register it under `resources` in `pygeoapi-config.yml`.
- Process handlers should accept validated, explicit arguments and return the shape expected by their processor adapter. Keep API metadata, model fields, handler parameters, and examples consistent.
- Use `get_config()` for all application configuration. It is a frozen, cached Pydantic model; call `get_config.cache_clear()` in a controlled test when a test needs to reload modified YAML.
- Use `processes.utils.session.load_session()` / `load_region()` for session lookup and standard missing/empty-session errors rather than duplicating path checks.
- Treat GeoServer layer aliases and KCS definitions as configuration. `layers.kcs` distinguishes raster/vector sources and declares the aggregation (`length`, `count`, `mean`, `max`, `min`, or `mode`); preserve those semantics when adding datasets.
- Keep generated artifacts in the configured session temp directory. Do not add generated rasters, GeoPackages, credentials, `.env`, `app.yml`, or local API cases to version control.
- Use module loggers (`logging.getLogger(__name__)`) and the project’s level policy in `LOGGING.md`: `INFO` for major workflow milestones, `DEBUG` for internals, `WARNING` for recoverable anomalies, and `ERROR`/`EXCEPTION` for failed operations. Do not call `logging.basicConfig()` from handlers or utility modules, and avoid per-feature/per-pixel INFO logging.
- Preserve the existing GeoServer publication behavior, including datastore path mapping, layer verification, and configured styles. Changes to publishing should be tested against a real GeoServer because the repository’s API cases depend on external layers and services.
- Configuration examples use container paths such as `/pygeoapi/tmp`; for native Windows execution, set `LARE_TMPDIR` to a Windows path and ensure the configured GeoServer can read the resulting files.

## Relevant documentation

- `README.md`: Docker/Compose operation, debugging, API-case runner, and the process-addition checklist.
- `README_geoserver.md`: external GeoServer datasets and which saved API cases exercise them.
- `LOGGING.md`: logging levels and performance expectations.
