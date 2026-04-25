"""FastAPI backend service for latGIS.

The service intentionally starts with an in-memory MVP API around explicit,
manual observations. It keeps the geospatial math in :mod:`latgis` while
providing stable request/response contracts that a future GUI can consume.
"""

from __future__ import annotations

from itertools import combinations
from uuid import uuid4

import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from latgis.geo.coord_transfers import CoordTransfers
from latgis.geo.triangulate import minDistPoint_3D
from latgis.location import CameraData, ItemLocation


app = FastAPI(
    title="latGIS Backend Service",
    version="0.1.0",
    description=(
        "API for registering georeferenced/oriented imagery, recording common "
        "point observations, and triangulating WGS84 coordinates."
    ),
)


class ProjectCreate(BaseModel):
    name: str = Field(default="Untitled project", min_length=1)
    description: str | None = None


class Project(ProjectCreate):
    id: str


class CameraPose(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    elevation: float = 0.0
    heading: float = Field(description="Compass heading/yaw in degrees, 0=N and 90=E.")
    pitch: float = Field(description="Camera pitch in degrees; positive angles upward.")
    roll: float | None = Field(
        default=None,
        description="Optional roll in degrees. Stored for clients; current core math does not consume roll.",
    )
    crs: str = "EPSG:4326"


class CameraIntrinsics(BaseModel):
    image_width: int = Field(default=1024, gt=0)
    image_height: int = Field(default=1024, gt=0)
    fov_degrees: float | None = Field(default=None, gt=0, lt=180)
    focal_length_pixels: float | None = Field(default=None, gt=0)
    principal_point_row: float | None = None
    principal_point_col: float | None = None


class ImageCreate(BaseModel):
    name: str = Field(min_length=1)
    uri: str | None = Field(default=None, description="External object-storage URI or local reference.")
    camera_pose: CameraPose
    intrinsics: CameraIntrinsics = Field(default_factory=CameraIntrinsics)
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class ImageAsset(ImageCreate):
    id: str


class ObservationCreate(BaseModel):
    image_id: str
    pixel_row: float
    pixel_col: float
    confidence: float | None = Field(default=None, ge=0, le=1)
    source: str = "manual"


class Observation(ObservationCreate):
    id: str


class TriangulationCreate(BaseModel):
    observation_ids: list[str] | None = Field(
        default=None,
        description="Observation IDs to use. If omitted, all project observations are used.",
    )


class CoordinateLLE(BaseModel):
    latitude: float
    longitude: float
    elevation: float


class CoordinateECEF(BaseModel):
    x: float
    y: float
    z: float


class TriangulationResult(BaseModel):
    id: str
    observation_ids: list[str]
    coordinate: CoordinateLLE
    ecef: CoordinateECEF
    estimated_error: float
    triangulation_count: int
    warnings: list[str] = Field(default_factory=list)


class ProjectState(BaseModel):
    project: Project
    images: dict[str, ImageAsset] = Field(default_factory=dict)
    observations: dict[str, Observation] = Field(default_factory=dict)
    triangulations: dict[str, TriangulationResult] = Field(default_factory=dict)


projects: dict[str, ProjectState] = {}
coord_transfers = CoordTransfers()


def _get_project(project_id: str) -> ProjectState:
    project = projects.get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' was not found.")
    return project


def _ray_from_observation(image: ImageAsset, observation: Observation) -> tuple[np.ndarray, np.ndarray]:
    pose = image.camera_pose
    camera = CameraData(
        LatLonEl=[pose.latitude, pose.longitude, pose.elevation],
        heading=pose.heading,
        pitch=pose.pitch,
    )
    item = ItemLocation(origCameraData=camera, origPixel=[observation.pixel_row, observation.pixel_col])
    return item.getRecentRayECEF()


def _finite_vector(value: object) -> bool:
    return isinstance(value, np.ndarray) and value.shape == (3,) and not np.isnan(value).any()


def _normalize_longitude(longitude: float) -> float:
    return ((longitude + 180.0) % 360.0) - 180.0


def _triangulate(project: ProjectState, observations: list[Observation]) -> TriangulationResult:
    if len(observations) < 2:
        raise HTTPException(status_code=400, detail="At least two observations are required.")

    rays: list[tuple[Observation, np.ndarray, np.ndarray]] = []
    warnings: list[str] = []
    for observation in observations:
        image = project.images.get(observation.image_id)
        if image is None:
            raise HTTPException(
                status_code=400,
                detail=f"Observation '{observation.id}' references unknown image '{observation.image_id}'.",
            )
        point, vector = _ray_from_observation(image, observation)
        rays.append((observation, point, vector))

    locations: list[np.ndarray] = []
    errors: list[float] = []
    for (obs_a, point_a, vector_a), (obs_b, point_b, vector_b) in combinations(rays, 2):
        if np.linalg.norm(np.cross(vector_a, vector_b)) < 1e-10:
            warnings.append(f"Observations '{obs_a.id}' and '{obs_b.id}' have near-parallel sight lines.")
            continue

        location, distance = minDistPoint_3D(vector_a, point_a, vector_b, point_b)
        if not _finite_vector(location):
            warnings.append(f"Observations '{obs_a.id}' and '{obs_b.id}' did not triangulate in front of both cameras.")
            continue

        locations.append(location)
        errors.append(float(distance))

    if not locations:
        raise HTTPException(status_code=422, detail="No valid triangulation could be computed.")

    ecef = np.mean(np.asarray(locations), axis=0)
    lle = coord_transfers.ECEF_to_LLE([float(ecef[0]), float(ecef[1]), float(ecef[2])])
    estimated_error = float(np.mean(errors) / np.sqrt(len(errors))) if errors else 0.0

    result = TriangulationResult(
        id=str(uuid4()),
        observation_ids=[observation.id for observation in observations],
        coordinate=CoordinateLLE(
            latitude=float(lle[0]),
            longitude=_normalize_longitude(float(lle[1])),
            elevation=float(lle[2]),
        ),
        ecef=CoordinateECEF(x=float(ecef[0]), y=float(ecef[1]), z=float(ecef[2])),
        estimated_error=estimated_error,
        triangulation_count=len(locations),
        warnings=warnings,
    )
    project.triangulations[result.id] = result
    return result


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/projects", response_model=Project, status_code=201)
def create_project(payload: ProjectCreate) -> Project:
    project = Project(id=str(uuid4()), **payload.model_dump())
    projects[project.id] = ProjectState(project=project)
    return project


@app.get("/projects/{project_id}", response_model=Project)
def get_project(project_id: str) -> Project:
    return _get_project(project_id).project


@app.post("/projects/{project_id}/images", response_model=ImageAsset, status_code=201)
def create_image(project_id: str, payload: ImageCreate) -> ImageAsset:
    project = _get_project(project_id)
    image = ImageAsset(id=str(uuid4()), **payload.model_dump())
    project.images[image.id] = image
    return image


@app.get("/projects/{project_id}/images/{image_id}/metadata", response_model=ImageAsset)
def get_image_metadata(project_id: str, image_id: str) -> ImageAsset:
    project = _get_project(project_id)
    image = project.images.get(image_id)
    if image is None:
        raise HTTPException(status_code=404, detail=f"Image '{image_id}' was not found.")
    return image


@app.post("/projects/{project_id}/observations", response_model=Observation, status_code=201)
def create_observation(project_id: str, payload: ObservationCreate) -> Observation:
    project = _get_project(project_id)
    if payload.image_id not in project.images:
        raise HTTPException(status_code=400, detail=f"Image '{payload.image_id}' was not found.")
    observation = Observation(id=str(uuid4()), **payload.model_dump())
    project.observations[observation.id] = observation
    return observation


@app.post("/projects/{project_id}/triangulations", response_model=TriangulationResult, status_code=201)
def create_triangulation(project_id: str, payload: TriangulationCreate) -> TriangulationResult:
    project = _get_project(project_id)
    if payload.observation_ids is None:
        observations = list(project.observations.values())
    else:
        observations = []
        for observation_id in payload.observation_ids:
            observation = project.observations.get(observation_id)
            if observation is None:
                raise HTTPException(status_code=400, detail=f"Observation '{observation_id}' was not found.")
            observations.append(observation)
    return _triangulate(project, observations)


@app.get("/projects/{project_id}/triangulations/{triangulation_id}", response_model=TriangulationResult)
def get_triangulation(project_id: str, triangulation_id: str) -> TriangulationResult:
    project = _get_project(project_id)
    triangulation = project.triangulations.get(triangulation_id)
    if triangulation is None:
        raise HTTPException(status_code=404, detail=f"Triangulation '{triangulation_id}' was not found.")
    return triangulation


@app.get("/projects/{project_id}/results.geojson")
def get_results_geojson(project_id: str) -> dict[str, object]:
    project = _get_project(project_id)
    features = []
    for result in project.triangulations.values():
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [
                        result.coordinate.longitude,
                        result.coordinate.latitude,
                        result.coordinate.elevation,
                    ],
                },
                "properties": {
                    "id": result.id,
                    "observation_ids": result.observation_ids,
                    "estimated_error": result.estimated_error,
                    "triangulation_count": result.triangulation_count,
                    "warnings": result.warnings,
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def main() -> int:
    import uvicorn

    uvicorn.run("latgis_service.app:app", host="127.0.0.1", port=8000)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
