from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_top_page():
    response = client.get("/")
    assert response.status_code == 200
    assert "SystemNavigator AI" in response.text
    assert "SystemNavigator <span>AI</span>" in response.text
    assert "AIシステム開発プラットフォーム" in response.text


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_docs():
    assert client.get("/docs").status_code == 200
