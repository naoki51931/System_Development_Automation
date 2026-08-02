from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_top_page():
    response = client.get("/")
    assert response.status_code == 200
    assert "SystemNavigator AI" in response.text
    assert "SystemNavigator <span>AI</span>" in response.text
    assert "AIシステム開発プラットフォーム" in response.text
    assert response.headers["content-type"].startswith("text/html")


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["content-type"].startswith("application/json")


def test_docs():
    assert client.get("/docs").status_code == 200


def test_openapi_contract_keeps_existing_paths():
    schema = client.get("/openapi.json")

    assert schema.status_code == 200
    assert schema.json()["info"]["title"] == "SystemNavigator AI"
    assert "/health" in schema.json()["paths"]


def test_unknown_api_path_returns_404():
    response = client.get("/api/v1/not-implemented")

    assert response.status_code == 404
