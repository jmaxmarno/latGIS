"""Desktop annotator app for the latGIS library."""

from __future__ import annotations

from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .annotator import ProjectStore, solve_observations

STATIC_DIR = Path(__file__).with_name("static")
INDEX_PATH = STATIC_DIR / "index.html"

app = FastAPI(
    title="latGIS Desktop Annotator",
    summary="Local-first image annotator and metadata editor for triangulation experiments.",
)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

STORE = ProjectStore()


class ObservationPayload(BaseModel):
    observation_id: str
    filename: str
    image_url: str | None = None
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    latitude: float | None = None
    longitude: float | None = None
    elevation_m: float | None = None
    heading_deg: float | None = None
    pitch_deg: float | None = None
    gps_accuracy_m: float | None = None
    captured_at: str | None = None
    pixel_row: float | None = None
    pixel_col: float | None = None
    source_metadata: dict = Field(default_factory=dict)


class SolveRequest(BaseModel):
    project_id: str | None = None
    observations: list[ObservationPayload]


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    """Serve the single-page desktop annotator."""
    return HTMLResponse(INDEX_PATH.read_text(encoding="utf-8"))


@app.get("/api/health")
def health() -> dict[str, str]:
    """Cheap health check for the local service."""
    return {"status": "ok"}


@app.post("/api/projects/upload")
async def upload_project(files: list[UploadFile] = File(...)) -> dict:
    """Create a local project from one or more uploaded images."""
    if not files:
        raise HTTPException(status_code=400, detail="Upload at least one image.")
    return await STORE.create_project(files)


@app.get("/api/projects/{project_id}")
def get_project(project_id: str) -> dict:
    """Return the current project snapshot."""
    project = STORE.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return project


@app.get("/api/projects/{project_id}/images/{observation_id}")
def get_project_image(project_id: str, observation_id: str) -> FileResponse:
    """Serve an uploaded image back to the browser."""
    image_path = STORE.get_image_path(project_id, observation_id)
    if image_path is None:
        raise HTTPException(status_code=404, detail="Image not found.")
    return FileResponse(image_path)


@app.post("/api/solve")
def solve(request: SolveRequest) -> dict:
    """Recompute previews and triangulation from the current observation edits."""
    project = STORE.get_project(request.project_id) if request.project_id else None
    observation_lookup = {}
    if project is not None:
        observation_lookup = {
            obs["observation_id"]: obs.get("image_url")
            for obs in project["observations"]
        }

    observations = []
    for observation in request.observations:
        payload = observation.model_dump()
        payload["image_url"] = payload.get("image_url") or observation_lookup.get(
            payload["observation_id"]
        )
        observations.append(payload)

    return solve_observations(observations)


def main() -> int:
    """Run the desktop annotator service."""
    uvicorn.run(app, host="127.0.0.1", port=8000)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
