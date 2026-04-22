# LARE — Landscape Archetype Restoration Engine

OGC API — Processes deployment using [pygeoapi](https://pygeoapi.io/). Configure offerings in `pygeoapi-config.yml` (see [publishing processes](https://dive.pygeoapi.io/publishing/ogcapi-processes/) in the pygeoapi workshop).

## Run with Docker

**Prerequisites:** [Docker](https://docs.docker.com/get-docker/) (on Windows, Docker Desktop must be running).

From the repository root:

```bash
docker compose up --build
```

- The API is served at **[http://localhost:5000](http://localhost:5000)** (host port `5000` maps to container port `80`).

### Development (default `docker-compose.yml`)

- **`processes/`**, **`app.yml`**, and **`./tmp`** are bind-mounted into the container.
- **`PYTHONPATH=/pygeoapi`** makes Python load the live `processes/` tree (over the copy installed by `pip install` in the image).

- Session directories from `lare-start` appear under **`./tmp`** on the host when `sdi.tmp.tmpdir` in `app.yml` is `/pygeoapi/tmp` (mapped to `./tmp`).
- After changing **`pyproject.toml`** dependencies, rebuild: `docker compose build --no-cache`.


### Config: temp directory override

Set environment variable **`LARE_TMPDIR`** to override `sdi.tmp.tmpdir` from `app.yml` (e.g. native Windows Python without Docker: `LARE_TMPDIR=C:\develop\lare\tmp`).

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

Instead of manually executing each endpoint in Swagger UI, you can run a local
test runner that posts your saved JSON payloads in sequence.

1. Create your local cases file (kept out of git):

```bash
cp tests/api_cases.example.json tests/api_cases.local.json
```

2. Edit `tests/api_cases.local.json` with your payloads.
   - Use `{{sessionid}}` in later steps; it is auto-filled from `lare-start`.
3. Run:

```bash
python scripts/run_api_tests.py --cases tests/api_cases.local.json
```

From the repository root, equivalent command:

```bash
python lare/tests/run_api_tests.py --mode sync --cases lare/tests/api_cases.local.json
```

Optional flags:
- `--base-url http://localhost:5000`
- `--timeout 180`

The runner exits with code `1` if any case fails (useful for CI later).

## Creating a New Process

To add a new process such as `process_new.py`:

1. Create a new input model in `processes/models.py`.
   Add a Pydantic model that defines and validates the request payload for the new process.

2. Implement the workflow in `processes/handlers/{new}.py`.
   Put the actual process logic in a handler function such as `mainhandler`. Keep file I/O, geospatial work, and publishing logic here.

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