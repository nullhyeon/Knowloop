from fastapi.testclient import TestClient

from knowloop_api.main import app

client = TestClient(app)


def test_root_endpoint_reports_service_status() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_process_health_endpoint_is_available() -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_api_health_endpoint_is_available() -> None:
    response = client.get("/api/v1/system/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
