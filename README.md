# latGIS

A geographical information systems object locator for coordinate determination.

`latgis` is a small Python library that triangulates the geodetic location
(latitude / longitude / elevation) of an object observed in two or more
camera frames given the cameras' positions, headings and pitches. The
`latgis_service` package now includes a local desktop annotator MVP for
uploading images, editing metadata, previewing sight lines on a map, and
reloading a triangulated result without building a full external API first.

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

- Python **3.12+**
- `numpy>=2,<3`, `pandas>=2,<3` (installed automatically)
- `fastapi`, `uvicorn`, `pillow`, `python-multipart` (installed automatically)

## Install (editable)

```bash
pip install -e .[dev]
```

## Run the tests

```bash
pytest
```

## Run the desktop annotator

```bash
latgis-service
```

Then open <http://127.0.0.1:8000>.

The annotator lets you:

- upload one or more photos from your phone
- extract whatever EXIF GPS metadata is available
- manually edit latitude, longitude, elevation, heading, pitch, and pixel
- click the image to place the target
- preview camera positions and sight lines on a map
- reload the triangulated result after metadata edits

The original triangulation pipeline remains in `src/latgis/` and is reused by
the annotator through thin wrapper code.

## Suggested capture companions

If you want heading / pitch / GPS accuracy visible during capture, start with:

- **Theodolite** (iOS)
- **Spyglass** (iOS / Android)

The desktop annotator still supports manual entry because phone metadata is
often incomplete or inconsistent.
