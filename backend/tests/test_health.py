from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import app, mount_frontend

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "pulse-backend"}


def test_built_dashboard_is_served_at_root_without_hiding_the_api(tmp_path):
    (tmp_path / "index.html").write_text("<!doctype html><title>PULSE</title>", encoding="utf-8")
    site = FastAPI()

    @site.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    assert mount_frontend(site, tmp_path)
    site_client = TestClient(site)
    assert "PULSE" in site_client.get("/").text
    assert site_client.get("/api/health").json() == {"status": "ok"}


def test_missing_dashboard_build_is_skipped(tmp_path):
    assert mount_frontend(FastAPI(), tmp_path) is False
