from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_health_and_ready_use_create_app_settings() -> None:
    cfg = Settings(
        app_name="CustomPlanTestApp",
        app_version="plan-test-1.0",
    )
    app = create_app(cfg)
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        body = health.json()
        assert body["app"] == "CustomPlanTestApp"
        assert body["version"] == "plan-test-1.0"

        ready = client.get("/ready")
        assert ready.status_code == 200
        rbody = ready.json()
        assert rbody["app"] == "CustomPlanTestApp"
        assert rbody["version"] == "plan-test-1.0"
        assert rbody["database"] == "up"
