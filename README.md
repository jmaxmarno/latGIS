# latGIS

A geographical information systems object locator for coordinate determination.

`latgis` is a small Python library that triangulates the geodetic location
(latitude / longitude / elevation) of an object observed in two or more
camera frames given the cameras' positions, headings and pitches. The
`latgis_service` package is a thin stub intended as the starting point for a
backend service exposing this functionality.

## Layout

```
src/
  latgis/                 # algorithmic library
    constants.py
    location.py           # CameraData, ItemLocation
    position_predict.py   # ItemLocationModel
    track.py              # TrackData, TargetTracker
    runner.py             # Runner stub
    geo/                  # coord transforms + triangulation
    tracking/             # vendored Munkres assignment
  latgis_service/         # backend-service entrypoint stub
tests/                    # pytest-discoverable unit tests
```

## Requirements

- Python **3.13+**
- `numpy>=2,<3`, `pandas>=2,<3` (installed automatically)

## Install (editable)

```bash
pip install -e .[dev]
```

## Run the tests

```bash
pytest
```

## Run the service stub

```bash
latgis-service
```

The `latgis-service` console script currently just instantiates `Runner` and
prints a message. Replace `src/latgis_service/app.py:main` with a real web
framework (FastAPI, Flask, ...) when wiring up the actual service.
