# LARE — Landscape Archetype Restoration Engine

OGC API — Processes deployment using [pygeoapi](https://pygeoapi.io/). Configure offerings in `pygeoapi-config.yml` (see [publishing processes](https://dive.pygeoapi.io/publishing/ogcapi-processes/) in the pygeoapi workshop).

## Run with Docker

**Prerequisites:** [Docker](https://docs.docker.com/get-docker/) (on Windows, Docker Desktop must be running).

From the repository root:

```bash
docker compose up --build
```

- The API is served at **[http://localhost:5000](http://localhost:5000)** (host port `5000` maps to container port `80`).
- Config is mounted from `./pygeoapi-config.yml` → `/pygeoapi/local.config.yml` inside the container.

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