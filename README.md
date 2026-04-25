# latGIS

A geographical information systems object locator for coordinate determination.

`latgis` is a small Python library that triangulates the geodetic location
(latitude / longitude / elevation) of an object observed in two or more
camera frames given the cameras' positions, headings and pitches. The
`latgis_service` package exposes that functionality as a FastAPI backend
service for future GUI clients.

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
  latgis_service/         # FastAPI backend-service entrypoint
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

## Run the service

```bash
latgis-service
```

The service starts on `http://127.0.0.1:8000`. FastAPI also exposes interactive
OpenAPI documentation at `http://127.0.0.1:8000/docs`.

Initial API workflow:

1. `POST /projects` to create a project/session.
2. `POST /projects/{project_id}/images` to register georeferenced/oriented
   images with camera pose and intrinsics metadata.
3. `POST /projects/{project_id}/observations` to record the common point pixel
   in each image.
4. `POST /projects/{project_id}/triangulations` to compute the output
   coordinate from two or more observations.
5. `GET /projects/{project_id}/results.geojson` to return GUI/map-ready
   triangulation results.

The current implementation is an in-memory MVP. It is intended to be backed by
PostgreSQL/PostGIS, object storage, and background workers as the service moves
toward production image ingestion and assisted point matching.
