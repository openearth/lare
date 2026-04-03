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
- **`run-with-hot-reload`** runs Gunicorn with `--reload` and reloads when `pygeoapi-config.yml` changes (see [pygeoapi Docker](https://docs.pygeoapi.io/en/latest/docker.html)). Worker count uses the image default (**4** Gunicorn workers) unless you set **`WSGI_WORKERS`**.
- Session directories from `lare-start` appear under **`./tmp`** on the host when `sdi.tmp.tmpdir` in `app.yml` is `/pygeoapi/tmp` (mapped to `./tmp`).
- After changing **`pyproject.toml`** dependencies, rebuild: `docker compose build --no-cache`.

### Production

Use an image built from the `Dockerfile` without mounting `./processes` or `./tmp`. Omit **`command`** (default is `run`) or set **`command: ["run"]`**, remove **`PYTHONPATH`**, and set **`WSGI_WORKERS`** as needed. Mount only your `pygeoapi-config.yml` (and `app.yml` if not baked into the image).

### Config: temp directory override

Set environment variable **`LARE_TMPDIR`** to override `sdi.tmp.tmpdir` from `app.yml` (e.g. native Windows Python without Docker: `LARE_TMPDIR=C:\develop\lare\tmp`).

Useful endpoints:


| URL | Purpose |
| --- | --- |
| [http://localhost:5000/](http://localhost:5000/) | Landing page |
| [http://localhost:5000/processes](http://localhost:5000/processes) | Process list |
| [http://localhost:5000/openapi](http://localhost:5000/openapi) | OpenAPI document / Swagger UI |


Run in the background:

```bash
docker compose up -d --build
```

Stop:

```bash
docker compose down
```

If port `5000` is already in use, change the left side of the port mapping in `docker-compose.yml` (e.g. `5001:80`).

## Legacy PyWPS

The previous PyWPS-based service and related files live under `lare-legacy/` and are not used by the Docker image above.

## License

GPL-3.0 (see `pygeoapi-config.yml` metadata).