"""latgis_service: backend-service surface for the latGIS library.

This package is intentionally a thin stub. Its purpose is to provide a clean,
importable namespace where a future web framework (e.g. FastAPI, Flask) or
job runner can live without polluting the algorithmic ``latgis`` package.
"""

from .app import main

__all__ = ["main"]
