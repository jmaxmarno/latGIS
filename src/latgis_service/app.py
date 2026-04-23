"""Entrypoint stub for the latGIS backend service.

This is deliberately framework-free. To turn it into an HTTP service later,
plug in FastAPI/Flask/Starlette here and expose ``Runner`` (and the rest of
:mod:`latgis`) over an API. The console-script ``latgis-service`` declared in
``pyproject.toml`` calls :func:`main`.
"""

from __future__ import annotations

from latgis import Runner


def main() -> int:
    """Run the latGIS backend service.

    Currently a no-op placeholder that instantiates the core
    :class:`latgis.Runner` so the wiring is exercised. Returns a process
    exit code (``0`` on success).
    """
    runner = Runner()
    print(f"latgis_service started (tracker_on={runner.tracker_on}). "
          "Replace this with a real service entrypoint (FastAPI, Flask, ...).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
