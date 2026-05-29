"""Tests for the Lattice web app (S6)."""
from starlette.testclient import TestClient
from lattice.web.app import app

client = TestClient(app)


def test_index_returns_200():
    response = client.get("/")
    assert response.status_code == 200


def test_index_returns_html_with_h1():
    response = client.get("/")
    assert "<h1>" in response.text


def test_index_content_type_is_html():
    response = client.get("/")
    assert "text/html" in response.headers["content-type"]


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_nonexistent_returns_404():
    response = client.get("/nonexistent")
    assert response.status_code == 404
