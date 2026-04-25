import numpy as np
from fastapi.testclient import TestClient

from latgis.constants import Constants
from latgis.geo.enu_to_ecef import MoreTransfers
from latgis_service.app import app, projects


client = TestClient(app)


def _aim_camera_at_target(camera_lle, target_lle):
    cam_ecef = np.asarray(MoreTransfers.geodetic2ecef(
        camera_lle[0], camera_lle[1], camera_lle[2], deg=True))
    tgt_ecef = np.asarray(MoreTransfers.geodetic2ecef(
        target_lle[0], target_lle[1], target_lle[2], deg=True))
    delta = tgt_ecef - cam_ecef

    lat0 = camera_lle[0] * np.pi / 180.0
    lon0 = camera_lle[1] * np.pi / 180.0
    rotation = np.array([
        [-np.sin(lon0), np.cos(lon0), 0.0],
        [-np.sin(lat0) * np.cos(lon0), -np.sin(lat0) * np.sin(lon0), np.cos(lat0)],
        [np.cos(lat0) * np.cos(lon0), np.cos(lat0) * np.sin(lon0), np.sin(lat0)],
    ])
    east, north, up = rotation @ delta
    return float(np.degrees(np.arctan2(east, north))), float(np.degrees(np.arctan2(up, np.hypot(east, north))))


def _create_image(project_id, name, camera_lle, target_lle):
    heading, pitch = _aim_camera_at_target(camera_lle, target_lle)
    response = client.post(
        f"/projects/{project_id}/images",
        json={
            "name": name,
            "camera_pose": {
                "latitude": camera_lle[0],
                "longitude": camera_lle[1],
                "elevation": camera_lle[2],
                "heading": heading,
                "pitch": pitch,
            },
            "intrinsics": {
                "image_width": Constants.SENSOR_SIZE[1],
                "image_height": Constants.SENSOR_SIZE[0],
            },
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_observation(project_id, image_id):
    response = client.post(
        f"/projects/{project_id}/observations",
        json={
            "image_id": image_id,
            "pixel_row": Constants.SENSOR_SIZE[0] / 2.0,
            "pixel_col": Constants.SENSOR_SIZE[1] / 2.0,
            "confidence": 1.0,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_manual_observation_triangulation_workflow():
    projects.clear()
    target_lle = [40.0, -75.0, 100.0]
    cam0_lle = [40.0, -75.0 + 200.0 / (111320.0 * np.cos(np.radians(40.0))), 100.0]
    cam1_lle = [40.0 + 200.0 / 111320.0, -75.0, 100.0]
    cam2_lle = [40.0, -75.0 - 200.0 / (111320.0 * np.cos(np.radians(40.0))), 100.0]

    project_response = client.post("/projects", json={"name": "triangulation test"})
    assert project_response.status_code == 201
    project_id = project_response.json()["id"]

    images = [
        _create_image(project_id, "image-a", cam0_lle, target_lle),
        _create_image(project_id, "image-b", cam1_lle, target_lle),
        _create_image(project_id, "image-c", cam2_lle, target_lle),
    ]
    observations = [_create_observation(project_id, image["id"]) for image in images]

    metadata_response = client.get(f"/projects/{project_id}/images/{images[0]['id']}/metadata")
    assert metadata_response.status_code == 200
    assert metadata_response.json()["camera_pose"]["crs"] == "EPSG:4326"

    triangulation_response = client.post(
        f"/projects/{project_id}/triangulations",
        json={"observation_ids": [observation["id"] for observation in observations]},
    )
    assert triangulation_response.status_code == 201, triangulation_response.text
    result = triangulation_response.json()
    assert result["triangulation_count"] == 3
    assert abs(result["coordinate"]["latitude"] - target_lle[0]) < 1e-5
    assert abs(result["coordinate"]["longitude"] - target_lle[1]) < 1e-5

    geojson_response = client.get(f"/projects/{project_id}/results.geojson")
    assert geojson_response.status_code == 200
    geojson = geojson_response.json()
    assert geojson["type"] == "FeatureCollection"
    assert geojson["features"][0]["geometry"]["type"] == "Point"
