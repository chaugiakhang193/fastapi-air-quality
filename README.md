# FastAPI Air Quality

This local application is a hands-on FastAPI learning project. It uses air quality
figures from the CAMS global forecast model through Open-Meteo. These are model
estimates, not measurements from monitoring stations.

## Quick start

```powershell
uv sync
uv run fastapi dev app/main.py
uv run pytest
```

## Data attribution

Air quality data come from the [Open-Meteo Air Quality API](https://open-meteo.com/en/docs/air-quality-api),
using [CAMS global atmospheric composition forecasts](https://ads.atmosphere.copernicus.eu/datasets/cams-global-atmospheric-composition-forecasts?tab=overview)
provided by the Copernicus Atmosphere Monitoring Service (CAMS).
Generated using Copernicus Atmosphere Monitoring Service information (2026).
The API data are available under [CC BY 4.0](https://open-meteo.com/en/terms).
Neither the European Commission nor ECMWF is responsible for any use of the
Copernicus information in this project; see the [Copernicus attribution terms](https://ads.atmosphere.copernicus.eu/licences/licence-to-use-copernicus-products).

## Status

Work in progress.
