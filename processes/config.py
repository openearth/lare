"""Centralised, read-once application configuration backed by Pydantic.

Usage
-----
    from processes.config import get_config

    cfg = get_config()
    print(cfg.tmpdir)
    print(cfg.geoserver.url)
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Dict, List

import yaml
from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Sub-models (mirror the YAML structure)
# ---------------------------------------------------------------------------

class GeoServerConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    url: str
    resturl: str
    workspace: str = "tmp"
    user: str
    password: str


class TmpConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    tmpdir: str


class SdiConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    geoserver: GeoServerConfig
    tmp: TmpConfig


class WfsNutsConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    url: str
    layer: str
    name_field: str


class OwsConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    base: str
    wfs_nuts: WfsNutsConfig


class LayersConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    datasets: Dict[str, str] = {}
    kcs: Dict[str, str] = {}
    dem: str
    clc: str
    eunis: str
    coastline: str
    imperviousness: str
    transport: str = ""
    population: str = ""


class HazardsConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    list: List[str]
    hazard: Dict[str, str]
    clc_scores: Dict[str, str] = {}


class ScoresConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    basecsv_path: str
    topo_hazards_csv: str


class PathsConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    tmp_base: str


class PostgisConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    host: str = "localhost"
    user: str = "postgres"
    password: str = ""
    database: str = ""


# ---------------------------------------------------------------------------
# Root model
# ---------------------------------------------------------------------------

class AppConfig(BaseModel):
    """Top-level config parsed from ``app.yml``."""

    model_config = ConfigDict(frozen=True)

    sdi: SdiConfig
    ows: OwsConfig
    layers: LayersConfig
    hazards: HazardsConfig
    hazard_layers: Dict[str, str] = {}
    scores: ScoresConfig
    paths: PathsConfig
    postgis: PostgisConfig = PostgisConfig()

    # -- convenience properties so callers keep using cfg.tmpdir etc. -------

    @property
    def tmpdir(self) -> str:
        return self.sdi.tmp.tmpdir

    @property
    def geoserver(self) -> GeoServerConfig:
        return self.sdi.geoserver

    @property
    def ows_base(self) -> str:
        return self.ows.base

    @property
    def wfs_nuts(self) -> WfsNutsConfig:
        return self.ows.wfs_nuts

    @property
    def datasets(self) -> Dict[str, str]:
        return self.layers.datasets

    @property
    def kcs(self) -> Dict[str, str]:
        return self.layers.kcs

    @property
    def layer_dem(self) -> str:
        return self.layers.dem

    @property
    def layer_clc(self) -> str:
        return self.layers.clc

    @property
    def layer_eunis(self) -> str:
        return self.layers.eunis

    @property
    def layer_coastline(self) -> str:
        return self.layers.coastline

    @property
    def layer_imperviousness(self) -> str:
        return self.layers.imperviousness

    @property
    def hazard_list(self) -> List[str]:
        return self.hazards.list

    @property
    def hazard_titles(self) -> Dict[str, str]:
        return self.hazards.hazard

    @property
    def hazard_clc_scores(self) -> Dict[str, str]:
        return self.hazards.clc_scores

    @property
    def topo_hazards_csv(self) -> str:
        return self.scores.topo_hazards_csv

    @property
    def basecsv_path(self) -> str:
        return self.scores.basecsv_path

    @property
    def tmp_base(self) -> str:
        return self.paths.tmp_base


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def _find_config_file(fn: str = "app.yml") -> Path:
    """Locate ``app.yml``, searching CWD first, then the project root."""
    candidate = Path(fn)
    if candidate.is_file():
        return candidate
    project_root = Path(__file__).resolve().parent.parent
    candidate = project_root / fn
    if candidate.is_file():
        return candidate
    raise FileNotFoundError(f"Config file not found: {fn}")


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    """Return the cached :class:`AppConfig` singleton.

    The YAML file is read and parsed exactly once per process lifetime.
    Call ``get_config.cache_clear()`` to force a reload.
    """
    path = _find_config_file()
    with open(path) as f:
        raw = yaml.safe_load(f)
    override = os.environ.get("LARE_TMPDIR")
    if override:
        raw.setdefault("sdi", {}).setdefault("tmp", {})["tmpdir"] = override
    return AppConfig.model_validate(raw)
