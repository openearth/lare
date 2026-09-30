# LARE — Landscape Resilience Explorer

OGC API — Processes deployment using [pygeoapi](https://pygeoapi.io/). Configure offerings in `pygeoapi-config.yml` (see [publishing processes](https://dive.pygeoapi.io/publishing/ogcapi-processes/) in the pygeoapi workshop).

## Run with Docker

**Prerequisites:** [Docker](https://docs.docker.com/get-docker/) (on Windows, Docker Desktop must be running).

From the repository root:

```bash
docker compose up --build
```

- The API is served at **[http://localhost:5000](http://localhost:5000)** (host port `5000` maps to container port `80`).
- `docker-compose.yml` contains shared settings.
- `docker-compose.override.yml` is loaded automatically for local development and enables live code mounts plus hot reload.
- `docker-compose.prod.yml` contains production overrides.

### Development (default Compose command)

- **`processes/`**, **`app.yml`**, and **`./tmp`** are bind-mounted into the container.
- **`PYTHONPATH=/pygeoapi`** makes Python load the live `processes/` tree (over the copy installed in the image).

- Session directories from `lare-start` appear under **`./tmp`** on the host when `sdi.tmp.tmpdir` in `app.yml` is `/pygeoapi/tmp` (mapped to `./tmp`).

### Updating Python dependencies

`pyproject.toml` lists the allowed dependencies; `uv.lock` records the resolved versions. Docker installs from the lock file into the base image's existing `/venv` without removing its other packages. No local Python or uv installation is needed.

After editing `pyproject.toml`, update `uv.lock` using the already-built project image (on a fresh checkout, run `docker compose build` first):

```powershell
# PowerShell, from the repository root
docker compose run --rm --no-deps -v "${PWD}:/workspace" -w /workspace --entrypoint uv pygeoapi lock --python /venv/bin/python
```

```bash
# Linux/macOS shell, from the repository root
docker compose run --rm --no-deps -v "$PWD:/workspace" -w /workspace --entrypoint uv pygeoapi lock --python /venv/bin/python
```

Review and commit both `pyproject.toml` and `uv.lock`, then rebuild with `docker compose build --no-cache`. The build uses `uv sync --locked` and fails if the manifest and lock file disagree, rather than choosing new dependency versions.


### Config: temp directory override

Set environment variable **`LARE_TMPDIR`** in the container to override `sdi.tmp.tmpdir` from `app.yml`. Use a container path that is mounted for session artifacts.

For Docker Compose, copy `.env.example` to `.env` and set **`LARE_TMPDIR_HOST`** to the absolute host path that GeoServer can read. Examples:

```bash
# Windows development
LARE_TMPDIR_HOST=C:/develop/lare/tmp

# Alma/Linux production
LARE_TMPDIR_HOST=/opt/lare/tmp
```

### Production on Alma/Linux

From `/opt/lare`:

```bash
mkdir -p tmp
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
```

The base Compose file defines the shared mounts. The production override adds `restart: unless-stopped`, sets `${LARE_TMPDIR_HOST:-/opt/lare/tmp}` as the GeoServer-visible temp directory, and adds `host.docker.internal` for Linux Docker hosts.

Useful endpoints:


| URL | Purpose |
| --- | --- |
| [http://localhost:5000/](http://localhost:5000/) | Landing page |
| [http://localhost:5000/processes](http://localhost:5000/processes) | Process list |
| [http://localhost:5000/openapi](http://localhost:5000/openapi) | OpenAPI document / Swagger UI |


Stop:

```bash
docker compose down
```

If port `5000` is already in use, change the left side of the port mapping in `docker-compose.yml` (e.g. `5001:80`).

### Debug API (Docker + debugpy)

1. Start with the debug override (exposes **5678** for the IDE):

```bash
docker compose -f docker-compose.yml -f docker-compose.debug.yml up --build
```

2. In Cursor/VS Code, start **Attach pygeoapi (Docker)** (`.vscode/launch.json`).

3. Set breakpoints under `processes/` and call the API as usual. For async jobs, add `Prefer: respond-async` to the request.

No changes inside process code are required; sync and async (TinyDB job threads) use the same attach.



Async responses are **202** with a **Location** (or **Link**) to the job; poll that URL until the job finishes, then open the results link from the job document.

### Run saved API test payloads

Instead of manually executing each endpoint in Swagger UI, run the saved API
test cases against the running Compose service from a container.

1. Copy the example cases file to `tests/api_cases.local.json` (kept out of git) and edit it with your payloads. Use `{{sessionid}}` in later steps; it is filled from `lare-start`.
2. With `docker compose up -d` running, execute the runner from the repository root:

```powershell
# PowerShell
docker compose run --rm --no-deps -v "${PWD}\tests:/pygeoapi/lare-tests:ro" --entrypoint /venv/bin/python pygeoapi /pygeoapi/lare-tests/run_api_tests.py --cases /pygeoapi/lare-tests/api_cases.local.json --base-url http://pygeoapi:80
```

```bash
# Linux/macOS shell
docker compose run --rm --no-deps -v "$PWD/tests:/pygeoapi/lare-tests:ro" --entrypoint /venv/bin/python pygeoapi /pygeoapi/lare-tests/run_api_tests.py --cases /pygeoapi/lare-tests/api_cases.local.json --base-url http://pygeoapi:80
```

Optional flags:
- `--timeout 180`

The runner exits with code `1` if any case fails (useful for CI later).

## Creating a New Process

To add a new process such as `process_new.py`:

1. Create a new input model in `processes/models.py`.
   Add a Pydantic model that defines and validates the request payload for the new process.

2. Implement the workflow in `processes/handlers/{new}.py`.
   Put the actual process logic in a handler function such as `main_handler`. Keep file I/O, geospatial work, and publishing logic here.

3. Create the pygeoapi processor in `processes/process_{new}.py`.
   Add a `PROCESS_METADATA` dictionary and a processor class such as `LareNewProcessor`.

4. Define clear process metadata.
   Include the process `id`, `title`, `description`, `jobControlOptions`, `inputs`, `outputs`, and an `example`. This metadata controls how the process appears in pygeoapi.

5. Register the process in `pygeoapi-config.yml`.
   Add a new entry under `resources:` that points to the processor class, for example `processes.process_new.LareNewProcessor`.

6. Reuse shared configuration from `processes/config.py`.
   Use `get_config()` for paths, GeoServer settings, layers, and the temp directory instead of hardcoding values.


7. After starting Docker, check that the new process appears at `/processes` and that it executes correctly through the API.

## License

GPL-3.0 (see `pygeoapi-config.yml` metadata).
