"""Helpers for the local latGIS image annotator."""

from __future__ import annotations

from pathlib import Path
from tempfile import mkdtemp
from typing import Any
from uuid import uuid4

import numpy as np
from fastapi import UploadFile
from PIL import ExifTags, Image

from latgis import CameraData, ItemLocation
from latgis.constants import Constants
from latgis.geo.coord_transfers import CoordTransfers

COORD_TRANSFERS = CoordTransfers()
EXIF_TAGS = ExifTags.TAGS
GPS_TAGS = ExifTags.GPSTAGS
SIGHTLINE_SAMPLE_METERS = [0.0, 25.0, 100.0, 250.0, 500.0, 1000.0, 2000.0]


def _as_float(value: Any) -> float | None:
    """Convert EXIF and JSON scalar values to floats."""
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        pass

    numerator = getattr(value, "numerator", None)
    denominator = getattr(value, "denominator", None)
    if numerator is not None and denominator:
        return float(numerator) / float(denominator)

    if isinstance(value, tuple) and len(value) == 2:
        numerator = _as_float(value[0])
        denominator = _as_float(value[1])
        if numerator is not None and denominator not in (None, 0):
            return numerator / denominator
    return None


def _dms_to_decimal(values: Any, ref: str | None) -> float | None:
    """Convert EXIF degrees/minutes/seconds to decimal degrees."""
    if not values or len(values) != 3:
        return None
    degrees = _as_float(values[0])
    minutes = _as_float(values[1])
    seconds = _as_float(values[2])
    if None in (degrees, minutes, seconds):
        return None

    decimal = degrees + minutes / 60.0 + seconds / 3600.0
    if ref in {"S", "W"}:
        decimal *= -1.0
    return decimal


def _normalize_longitude(lon_deg: float | None) -> float | None:
    """Convert [0, 360) longitudes back into [-180, 180)."""
    if lon_deg is None:
        return None
    return ((lon_deg + 180.0) % 360.0) - 180.0


def _image_exif(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return decoded EXIF and GPS tags for an image."""
    with Image.open(path) as image:
        raw_exif = image.getexif()

    decoded_exif = {
        EXIF_TAGS.get(tag, tag): value
        for tag, value in raw_exif.items()
    }
    raw_gps = decoded_exif.get("GPSInfo") or {}
    decoded_gps = {
        GPS_TAGS.get(tag, tag): value
        for tag, value in raw_gps.items()
    }
    return decoded_exif, decoded_gps


def _extract_metadata(path: Path) -> dict[str, Any]:
    """Extract best-effort GPS and orientation metadata from EXIF."""
    exif, gps = _image_exif(path)
    latitude = _dms_to_decimal(gps.get("GPSLatitude"), gps.get("GPSLatitudeRef"))
    longitude = _dms_to_decimal(gps.get("GPSLongitude"), gps.get("GPSLongitudeRef"))
    altitude = _as_float(gps.get("GPSAltitude"))
    altitude_ref = _as_float(gps.get("GPSAltitudeRef"))
    if altitude is not None and altitude_ref == 1:
        altitude *= -1.0

    heading = _as_float(gps.get("GPSImgDirection"))
    accuracy = _as_float(gps.get("GPSHPositioningError"))
    captured_at = exif.get("DateTimeOriginal") or exif.get("DateTime")

    source_metadata = {
        "exif_heading_tag": "GPSImgDirection" if heading is not None else None,
        "pitch_source": None,
        "gps_accuracy_tag": "GPSHPositioningError" if accuracy is not None else None,
    }

    return {
        "latitude": latitude,
        "longitude": longitude,
        "elevation_m": altitude,
        "heading_deg": heading,
        "pitch_deg": None,
        "gps_accuracy_m": accuracy,
        "captured_at": captured_at,
        "source_metadata": {
            key: value for key, value in source_metadata.items() if value is not None
        },
    }


def _normalize_pixel(pixel_row: float | None,
                     pixel_col: float | None,
                     width: int,
                     height: int) -> list[float] | None:
    """Scale native image pixels onto the original triangulation sensor frame."""
    if None in (pixel_row, pixel_col):
        return None

    return [
        float(pixel_row) * Constants.SENSOR_SIZE[0] / float(height),
        float(pixel_col) * Constants.SENSOR_SIZE[1] / float(width),
    ]


def _camera_data_from_observation(observation: dict[str, Any]) -> CameraData | None:
    """Create CameraData if the required fields are present."""
    latitude = _as_float(observation.get("latitude"))
    longitude = _as_float(observation.get("longitude"))
    elevation = _as_float(observation.get("elevation_m"))
    heading = _as_float(observation.get("heading_deg"))
    pitch = _as_float(observation.get("pitch_deg"))

    if None in (latitude, longitude, elevation, heading, pitch):
        return None

    return CameraData(
        LatLonEl=[latitude, longitude, elevation],
        heading=heading,
        pitch=pitch,
    )


def _build_sightline(camera: CameraData, normalized_pixel: list[float]) -> list[dict[str, float]]:
    """Project one observation's line of sight into map-ready points."""
    item = ItemLocation(origCameraData=camera, origPixel=normalized_pixel)
    ecef_pt = item.getRecentECEFPoint()
    ecef_vec = item.getRecentECEFVector()

    points = []
    for sample_m in SIGHTLINE_SAMPLE_METERS:
        sample_ecef = ecef_pt + ecef_vec * sample_m
        lat, lon, elev = COORD_TRANSFERS.ECEF_to_LLE(sample_ecef)
        points.append(
            {
                "latitude": float(lat),
                "longitude": float(_normalize_longitude(float(lon))),
                "elevation_m": float(elev),
            }
        )

    return points


def _triangulate(observations: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Run the existing triangulation pipeline over ready observations."""
    if len(observations) < 2:
        return None

    first = observations[0]
    item = ItemLocation(
        origCameraData=first["camera_data"],
        origPixel=first["normalized_pixel"],
    )
    for observation in observations[1:]:
        item.addNewObservation(
            cameraData=observation["camera_data"],
            pixel=observation["normalized_pixel"],
        )

    triangulated_lle, triangulation_error, num_locations = item.computeResults()
    if isinstance(triangulated_lle, float) and np.isnan(triangulated_lle):
        return None

    triangulated_lle = np.asarray(triangulated_lle, dtype=float)
    if np.isnan(triangulated_lle).any():
        return None

    lat, lon, elev = triangulated_lle.tolist()
    return {
        "triangulated_location": {
            "latitude": float(lat),
            "longitude": float(_normalize_longitude(float(lon))),
            "elevation_m": float(elev),
        },
        "triangulation_error": (
            None if triangulation_error is None or np.isnan(triangulation_error)
            else float(triangulation_error)
        ),
        "num_locations": int(num_locations),
    }


def extract_observation_from_image(path: Path,
                                   observation_id: str,
                                   image_url: str) -> dict[str, Any]:
    """Build the browser-facing observation payload for one image."""
    with Image.open(path) as image:
        width, height = image.size

    extracted = _extract_metadata(path)
    center_row = height / 2.0
    center_col = width / 2.0
    return {
        "observation_id": observation_id,
        "filename": path.name,
        "image_url": image_url,
        "width": width,
        "height": height,
        "latitude": extracted["latitude"],
        "longitude": extracted["longitude"],
        "elevation_m": extracted["elevation_m"],
        "heading_deg": extracted["heading_deg"],
        "pitch_deg": extracted["pitch_deg"],
        "gps_accuracy_m": extracted["gps_accuracy_m"],
        "captured_at": extracted["captured_at"],
        "pixel_row": center_row,
        "pixel_col": center_col,
        "source_metadata": extracted["source_metadata"],
    }


def solve_observations(observations: list[dict[str, Any]]) -> dict[str, Any]:
    """Prepare map previews and run triangulation for ready observations."""
    ready_observations = []
    response_observations = []
    issues = []

    for observation in observations:
        width = int(observation["width"])
        height = int(observation["height"])
        pixel_row = _as_float(observation.get("pixel_row"))
        pixel_col = _as_float(observation.get("pixel_col"))
        normalized_pixel = _normalize_pixel(pixel_row, pixel_col, width, height)

        response_observation = dict(observation)
        response_observation["normalized_pixel"] = (
            None
            if normalized_pixel is None
            else {
                "row": normalized_pixel[0],
                "col": normalized_pixel[1],
            }
        )
        response_observation["status"] = "incomplete"
        response_observation["camera_point"] = None
        response_observation["sightline"] = []

        camera_data = _camera_data_from_observation(observation)
        if normalized_pixel is None or camera_data is None:
            issues.append(
                f"{observation['filename']}: add location, heading, pitch, elevation, and a selected pixel."
            )
            response_observations.append(response_observation)
            continue

        camera_lat, camera_lon, camera_elev = camera_data.LatLonEl
        response_observation["camera_point"] = {
            "latitude": float(camera_lat),
            "longitude": float(camera_lon),
            "elevation_m": float(camera_elev),
        }
        response_observation["sightline"] = _build_sightline(camera_data, normalized_pixel)
        response_observation["status"] = "ready"

        ready_observations.append(
            {
                "camera_data": camera_data,
                "normalized_pixel": normalized_pixel,
            }
        )
        response_observations.append(response_observation)

    triangulation = _triangulate(ready_observations)
    return {
        "observations": response_observations,
        "issues": issues,
        "result": triangulation,
    }


class ProjectStore:
    """Tiny local store for uploaded annotator sessions."""

    def __init__(self) -> None:
        self.root = Path(mkdtemp(prefix="latgis-annotator-"))
        self.projects: dict[str, dict[str, Any]] = {}

    async def create_project(self, files: list[UploadFile]) -> dict[str, Any]:
        """Persist uploaded files and return the initial project payload."""
        project_id = uuid4().hex
        project_dir = self.root / project_id
        project_dir.mkdir(parents=True, exist_ok=True)

        observations = []
        image_paths = {}
        for index, upload in enumerate(files):
            suffix = Path(upload.filename or f"image-{index}.jpg").suffix or ".jpg"
            observation_id = uuid4().hex
            filename = f"{index:02d}-{observation_id}{suffix}"
            destination = project_dir / filename
            destination.write_bytes(await upload.read())
            image_url = f"/api/projects/{project_id}/images/{observation_id}"
            observations.append(
                extract_observation_from_image(
                    destination,
                    observation_id=observation_id,
                    image_url=image_url,
                )
            )
            image_paths[observation_id] = destination

        project = {
            "project_id": project_id,
            "observations": observations,
            "analysis": solve_observations(observations),
        }
        self.projects[project_id] = {
            "project": project,
            "image_paths": image_paths,
        }
        return project

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        """Return a saved project payload."""
        entry = self.projects.get(project_id)
        if entry is None:
            return None
        return entry["project"]

    def get_image_path(self, project_id: str, observation_id: str) -> Path | None:
        """Resolve an uploaded image path."""
        entry = self.projects.get(project_id)
        if entry is None:
            return None
        return entry["image_paths"].get(observation_id)
