"""FastAPI entry point for the PULSE backend.

Run locally (from the backend folder, venv active):
    uvicorn app.main:app --reload
"""

from fastapi import FastAPI

from app.api.routes import router

app = FastAPI(title="PULSE API", version="0.1.0")
app.include_router(router)


@app.get("/api/health")
def health() -> dict[str, str]:
    """Liveness check used by tests, the frontend, and (later) the host."""
    return {"status": "ok", "service": "pulse-backend"}
