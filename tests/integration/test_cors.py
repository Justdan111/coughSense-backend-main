"""CORS preflight + actual-request behavior."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


def test_cors_preflight_allows_localhost_3000(client: TestClient):
    r = client.options(
        "/api/auth/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r.status_code in (200, 204)
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_cors_actual_request_includes_allow_origin(client: TestClient):
    r = client.get(
        "/api/auth/health",
        headers={"Origin": "http://localhost:3000"},
    )
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_cors_other_origin_not_echoed(client: TestClient):
    r = client.get(
        "/api/auth/health",
        headers={"Origin": "http://evil.example.com"},
    )
    # The endpoint still works — CORS is browser-enforced — but the allow-origin
    # header should NOT be set for an origin that's not in the allow-list.
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") != "http://evil.example.com"
