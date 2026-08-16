"""
Smoke test for Milestone 2: proves the FastAPI app boots and the test
harness (pytest + TestClient) actually works before any real agent logic
is layered on top. Every later milestone builds on this passing.
"""
from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)


def test_health_check_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "env" in body
