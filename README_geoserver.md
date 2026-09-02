# LARE test datasets

This document lists every dataset referenced in `app.yml`, whether it is exercised by the API test cases, and its data source.

Test cases all use region **Cantabria** on layer `region:nuts_2021`.

## Accessing the local GeoServer drive

To access the internal GeoServer files referenced in this document, first map the shared drive in PowerShell:

```powershell
pushd \\c-oet25568.directory.intra\appdata
```

This is the network location behind the `Z:` drive used in the dataset paths below.

| Where mentioned | Name | Workspace | Data source | Used in tests |
|---|---|---|---|---|
| `app.yml` → `layers.datasets`; tests → `layer_name` | `nuts_2021` | `region` | Local GeoServer — `Z:\geoserver\desirmed\nuts\nuts_2021.gpkg` | Yes — all cases |
| `app.yml` → `layers.clc`; `lare-uom` | `U2018_CLC2018_V2020_20u1_cog` | `landuse` | Local GeoServer — `Z:\geoserver\desirmed\landuse\U2018_CLC2018_V2020_20u1_cog.tif` | Yes — all cases |
| `app.yml` → `layers.coastline`; `lare-uom` (`archetype: coastal`) | `coastlines2` | `coast` | Local GeoServer — `Z:\geoserver\desirmed\osmcoastline\coastlines-split-3857\coastline.gpkg` | Yes — UC2, UC4, UC8 |
| `app.yml` → `layers.kcs`; tests → `kcs: "transport"` | `transport` | `transport` | Local GeoServer — `Z:\geoserver\desirmed\transport\transport.gpkg` | Yes — UC2, UC8 |
| `app.yml` → `layers.kcs`; tests → `kcs: "agriculture"` | `agriculture` | `agriculture` | Local GeoServer — `Z:\geoserver\desirmed\landuse\U2018_CLC2018_V2020_20u1_cog.tif` | Yes — UC3, UC4, UC7 |
| `app.yml` → `layers.kcs`; tests → `kcs: "hospitals"` | `hospitals` | `socio_economic` | PostgreSQL — machine `c-oet25568.directory.intra`, database `desirmed` | Yes — UC5, UC6 |
| `app.yml` → `hazard_layers.pluvial_RP200`; tests → `hazard: "pluvial_RP200"` | `Europe_RP200_filled_depth` | `hazard` | Local GeoServer — `Z:\geoserver\desirmed\hazard\pluvial\Europe_RP200_filled_depth.tif` | Yes — UC2, UC8 |
| `app.yml` → `hazard_layers.drought`; tests → `hazard: "drought"` | `cdinx_mode_over_time` | `hazard` | Local GeoServer — `Z:\geoserver\desirmed\drought\cdinx_mode_over_time.tif` | Yes — UC3, UC7 |
| `app.yml` → `hazard_layers.salinity`; tests → `hazard: "salinity"` | `salinity` | `hazard` | Local GeoServer — `Z:\geoserver\desirmed\salinity\soil_salinity_2016_europe.tif` | Yes — UC4 |
| `app.yml` → `hazard_layers.heat`; tests → `hazard: "heat"` | `utci_days_above_46_daily_max` | `hazard` | Local GeoServer — `Z:\geoserver\desirmed\heat\utci_days_above_46_daily_max.tif` | Yes — UC5, UC6 |
| `app.yml` → `hazards.clc_scores.archetype` | `landscapearchetype.csv` | — (`data/`) | GitHub — `data/` | Yes — all cases |
| `app.yml` → `nbs.table`; `lare-nbs` | `clc_nbs_hazard_updated.csv` | — (`data/`) | GitHub — `data/` | Yes — UC6, UC7, UC8 |
| `app.yml` → `layers.datasets` | `hybas_eu_lev12_v1c` | `hydro` | Local GeoServer | **Not used yet** |
| `app.yml` → `layers.kcs` | `pop2020` | `socio_economic` | Local GeoServer | **Not used yet** |
| `app.yml` → `layers.kcs` | `pop2030` | `socio_economic` | Local GeoServer | **Not used yet** |
| `app.yml` → `layers.kcs` | `elderly_facilities` | `socio_economic` | Local GeoServer | **Not used yet** |
| `app.yml` → `layers.dem` | `dem` | `topography` | Local GeoServer | **Not used yet** |
| `app.yml` → `layers.transport` | `transport` | `topography` | Local GeoServer | **Not used yet** |
| `app.yml` → `layers.eunis` | `eea_r_3035_100m_v3-1_cog` | `landuse` | Local GeoServer | **Not used yet** |
| `app.yml` → `layers.imperviousness` | `imperviousness` | `imperviousness` | Local GeoServer | **Not used yet** |
| `app.yml` → `layers.population` | `pop2020` | `socio_economic` | Local GeoServer | **Not used yet** |
| `app.yml` → `hazard_layers.pluvial_RP10` | `Europe_RP10_filled_depth` | `hazard` | Local GeoServer | **Not used yet** |
| `app.yml` → `hazard_layers.pluvial_RP20` | `Europe_RP20_filled_depth` | `hazard` | Local GeoServer | **Not used yet** |
| `app.yml` → `hazard_layers.pluvial_RP50` | `Europe_RP50_filled_depth` | `hazard` | Local GeoServer | **Not used yet** |
| `app.yml` → `hazard_layers.pluvial_RP75` | `Europe_RP75_filled_depth` | `hazard` | Local GeoServer | **Not used yet** |
| `app.yml` → `hazard_layers.pluvial_RP100` | `Europe_RP100_filled_depth` | `hazard` | Local GeoServer | **Not used yet** *(referenced only in `api_cases.example.json`)* |
| `app.yml` → `scores.topo_hazards_csv` | `topo_hazards.csv` | — (`data/`) | GitHub — `data/` | **Not used yet** |