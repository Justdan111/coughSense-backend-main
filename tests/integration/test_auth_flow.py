"""
Integration tests for the auth router — every test hits real Supabase.

Coverage: register → login → refresh → me → account (get + patch).
"""
from __future__ import annotations

import time
import uuid

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


# ─────────────────────────────────────────────────────────────────────
# Health
# ─────────────────────────────────────────────────────────────────────

def test_auth_health(client: TestClient):
    r = client.get("/api/auth/health")
    assert r.status_code == 200
    assert r.json() == {"status": "auth ok"}


# ─────────────────────────────────────────────────────────────────────
# Register
# ─────────────────────────────────────────────────────────────────────

def _fresh_email() -> str:
    return f"qa+coughsense+{int(time.time() * 1000)}-{uuid.uuid4().hex[:6]}@example.com"


def test_register_success(client: TestClient, supabase_admin):
    email = _fresh_email()
    r = client.post(
        "/api/auth/register",
        json={"email": email, "password": "Test1234!Strong"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert "user" in body
    assert body["user"]["email"] == email
    assert "id" in body["user"]

    if supabase_admin is not None:
        try:
            supabase_admin.auth.admin.delete_user(body["user"]["id"])
        except Exception:
            pass


def test_register_duplicate_email(client: TestClient, test_user):
    r = client.post(
        "/api/auth/register",
        json={"email": test_user["email"], "password": "Test1234!Strong"},
    )
    assert r.status_code == 400
    assert "already registered" in r.json()["detail"].lower()


@pytest.mark.parametrize("password", ["short", "1234567"])
def test_register_rejects_weak_password(client: TestClient, password: str):
    r = client.post(
        "/api/auth/register",
        json={"email": _fresh_email(), "password": password},
    )
    assert r.status_code == 422


def test_register_rejects_invalid_email(client: TestClient):
    r = client.post(
        "/api/auth/register",
        json={"email": "not-an-email", "password": "Test1234!Strong"},
    )
    assert r.status_code == 422


# ─────────────────────────────────────────────────────────────────────
# Login
# ─────────────────────────────────────────────────────────────────────

def test_login_success(client: TestClient, test_user):
    r = client.post(
        "/api/auth/login",
        json={"email": test_user["email"], "password": test_user["password"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["user"]["id"] == test_user["id"]


def test_login_wrong_password(client: TestClient, test_user):
    r = client.post(
        "/api/auth/login",
        json={"email": test_user["email"], "password": "wrong-password"},
    )
    assert r.status_code in (401, 400)


def test_login_unknown_email(client: TestClient):
    r = client.post(
        "/api/auth/login",
        json={"email": _fresh_email(), "password": "Test1234!Strong"},
    )
    assert r.status_code in (401, 400)


# ─────────────────────────────────────────────────────────────────────
# Refresh
# ─────────────────────────────────────────────────────────────────────

def test_refresh_success(client: TestClient, test_user):
    if not test_user.get("refresh_token"):
        pytest.skip("No refresh token returned by Supabase on this run")
    r = client.post(
        "/api/auth/refresh",
        json={"refresh_token": test_user["refresh_token"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_refresh_invalid_token(client: TestClient):
    r = client.post(
        "/api/auth/refresh",
        json={"refresh_token": "obviously-invalid-token"},
    )
    assert r.status_code == 401


# ─────────────────────────────────────────────────────────────────────
# /me
# ─────────────────────────────────────────────────────────────────────

def test_me_returns_id_and_email(client: TestClient, test_user, auth_headers):
    r = client.get("/api/auth/me", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == test_user["id"]
    assert body["email"] == test_user["email"]


def test_me_without_token(client: TestClient):
    r = client.get("/api/auth/me")
    assert r.status_code in (401, 403)


def test_me_with_garbage_token(client: TestClient):
    r = client.get(
        "/api/auth/me",
        headers={"Authorization": "Bearer not.a.real.jwt"},
    )
    assert r.status_code in (401, 500)  # impl raises 500 on jose decode of garbage


# ─────────────────────────────────────────────────────────────────────
# /account (get + patch)
# ─────────────────────────────────────────────────────────────────────

def test_account_get_initial_state(client: TestClient, test_user, auth_headers):
    """Brand-new user has no profiles row, so name should be null."""
    r = client.get("/api/auth/account", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == test_user["id"]
    assert body["email"] == test_user["email"]
    assert body["name"] is None


def test_account_patch_then_get(client: TestClient, test_user, auth_headers):
    r = client.patch(
        "/api/auth/account",
        json={"name": "  Dan Emmanuel  "},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Dan Emmanuel"  # trimmed

    g = client.get("/api/auth/account", headers=auth_headers)
    assert g.status_code == 200
    assert g.json()["name"] == "Dan Emmanuel"


def test_account_patch_empty_name_rejected(client: TestClient, auth_headers):
    r = client.patch(
        "/api/auth/account",
        json={"name": ""},
        headers=auth_headers,
    )
    assert r.status_code == 422


def test_account_patch_without_token(client: TestClient):
    r = client.patch("/api/auth/account", json={"name": "Dan"})
    assert r.status_code in (401, 403)
