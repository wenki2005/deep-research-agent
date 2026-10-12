from fastapi.testclient import TestClient

from research_agent.api import app


def test_health():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_config_does_not_expose_secrets():
    response = TestClient(app).get("/config")
    assert response.status_code == 200
    assert "TAVILY_API_KEY" not in response.text
