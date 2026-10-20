"""FastAPI entry point for the PULSE backend.

Run locally (from the backend folder, venv active):
    uvicorn app.main:app --reload

In production the same server also serves the built dashboard (frontend/dist),
so the whole app is one service and one URL.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import router

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"

app = FastAPI(title="PULSE API", version="0.1.0")
app.include_router(router)


@app.get("/api/health")
def health() -> dict[str, str]:
    """Liveness check used by tests, the frontend, and the host."""
    return {"status": "ok", "service": "pulse-backend"}


def mount_frontend(target: FastAPI, dist: Path) -> bool:
    """Serve the built dashboard at "/" (after all /api routes). Skipped if it isn't built."""
    if not (dist / "index.html").exists():
        return False
    target.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    return True


mount_frontend(app, FRONTEND_DIST)
