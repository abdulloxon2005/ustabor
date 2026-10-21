import importlib

from fastapi.testclient import TestClient

from app.core.config import settings
import app.main as main_mod


def test_health_ok(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"


def test_cors_allows_frontend_origin(client):
    r = client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:5500",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:5500"


def test_cors_blocks_unknown_origin(client):
    r = client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" not in r.headers


def test_docs_and_openapi_disabled_in_production(client, monkeypatch):
    # Development holatida /docs va /openapi.json ochiq
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200

    orig_app = main_mod.app
    try:
        monkeypatch.setattr(settings, "ENVIRONMENT", "production")
        importlib.reload(main_mod)
        with TestClient(main_mod.app) as prod_client:
            assert prod_client.get("/docs").status_code == 404
            assert prod_client.get("/redoc").status_code == 404
            assert prod_client.get("/openapi.json").status_code == 404
            assert prod_client.get("/api/v1/health").status_code == 200
    finally:
        monkeypatch.undo()
        main_mod.app = orig_app
        main_mod._is_prod = False
