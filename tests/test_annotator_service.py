"""Tests for the desktop annotator scaffolding."""

from __future__ import annotations

from io import BytesIO

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

from latgis.constants import Constants
from latgis_service.annotator import extract_observation_from_image, solve_observations
from latgis_service.app import app
from tests.test_planted_target import _aim_camera_at_target


def _make_image_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (640, 480), color=(32, 64, 128)).save(buffer, format="JPEG")
    return buffer.getvalue()


def test_extract_observation_defaults_to_image_center(tmp_path):
    image_path = tmp_path / "capture.jpg"
    image_path.write_bytes(_make_image_bytes())

    observation = extract_observation_from_image(
        image_path,
        observation_id="obs-1",
        image_url="/images/obs-1",
    )

    assert observation["width"] == 640
    assert observation["height"] == 480
    assert observation["pixel_row"] == 240.0
    assert observation["pixel_col"] == 320.0
    assert observation["latitude"] is None


def test_solve_observations_produces_triangulated_location():
    target_lle = [40.0, -75.0, 100.0]
    cam0_lle = [40.0, -75.0 + 200.0 / (111320.0 * np.cos(np.radians(40.0))), 100.0]
    cam1_lle = [40.0 + 200.0 / 111320.0, -75.0, 100.0]
    h0, p0 = _aim_camera_at_target(cam0_lle, target_lle)
    h1, p1 = _aim_camera_at_target(cam1_lle, target_lle)

    center = [Constants.SENSOR_SIZE[0] / 2.0, Constants.SENSOR_SIZE[1] / 2.0]
    observations = [
        {
            "observation_id": "one",
            "filename": "one.jpg",
            "image_url": "/one.jpg",
            "width": 1024,
            "height": 1024,
            "latitude": cam0_lle[0],
            "longitude": cam0_lle[1],
            "elevation_m": cam0_lle[2],
            "heading_deg": h0,
            "pitch_deg": p0,
            "gps_accuracy_m": None,
            "captured_at": None,
            "pixel_row": center[0],
            "pixel_col": center[1],
            "source_metadata": {},
        },
        {
            "observation_id": "two",
            "filename": "two.jpg",
            "image_url": "/two.jpg",
            "width": 1024,
            "height": 1024,
            "latitude": cam1_lle[0],
            "longitude": cam1_lle[1],
            "elevation_m": cam1_lle[2],
            "heading_deg": h1,
            "pitch_deg": p1,
            "gps_accuracy_m": None,
            "captured_at": None,
            "pixel_row": center[0],
            "pixel_col": center[1],
            "source_metadata": {},
        },
    ]

    solved = solve_observations(observations)
    triangulated = solved["result"]["triangulated_location"]

    assert triangulated is not None
    assert abs(triangulated["latitude"] - target_lle[0]) < 1e-4
    assert abs(triangulated["longitude"] - target_lle[1]) < 1e-4


def test_upload_endpoint_returns_project():
    client = TestClient(app)

    response = client.post(
        "/api/projects/upload",
        files=[("files", ("capture.jpg", _make_image_bytes(), "image/jpeg"))],
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["project_id"]
    assert len(payload["observations"]) == 1
    assert payload["observations"][0]["image_url"].startswith("/api/projects/")
