"""
Shared pytest fixtures for the CoughSense test suite.

Layered design:
    - `client`             — FastAPI TestClient, no auth, no network
    - `supabase_admin`     — Supabase client with the service-role key, used
                              ONLY for cleanup. None if SUPABASE_SERVICE_ROLE_KEY
                              is not set (orphan users will accumulate).
    - `test_user`          — function-scoped real Supabase user; teardown
                              deletes the user via admin client when possible
    - `auth_headers`       — Bearer header derived from `test_user`
    - JWT helpers          — fixtures that mint expired/wrong-aud/malformed
                              tokens with the real JWT secret for negative
                              auth-dep tests
    - `audio_fixture`      — opens a fixture WAV and returns the multipart
                              tuple ready for `client.post(..., files=...)`
"""
from __future__ import annotations

import os
import time
import uuid
from pathlib import Path
from typing import Any, Iterator

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

# Load .env.test BEFORE importing the app — the app reads env vars at
# import time (see app/core/config.py and app/deps/auth.py). pytest-env
# also handles this via env_files, but loading explicitly here makes the
# behavior predictable when running outside pytest.
_ENV_TEST = Path(__file__).parent.parent / ".env.test"
if _ENV_TEST.exists():
    load_dotenv(_ENV_TEST, override=True)


# ─────────────────────────────────────────────────────────────────────
# Audio fixtures — generated once per session
# ─────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session", autouse=True)
def _ensure_audio_fixtures() -> dict[str, Path]:
    from tests.fixtures.audio_factory import ensure_all
    return ensure_all()


@pytest.fixture
def audio_fixture():
    """
    Returns a callable: name → (filename, content_bytes, mime_type)
    Use it as: client.post("/api/analysis/analyze", files={"audio": audio_fixture("synthetic_cough.wav")})
    """
    base = Path(__file__).parent / "fixtures" / "audio"

    def _open(name: str, mime: str = "audio/wav") -> tuple[str, bytes, str]:
        path = base / name
        if not path.exists():
            pytest.skip(f"Audio fixture missing: {path}")
        return (name, path.read_bytes(), mime)

    return _open


# ─────────────────────────────────────────────────────────────────────
# FastAPI client
# ─────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def client() -> Iterator[TestClient]:
    # Imported lazily so .env.test is loaded first.
    from app.main import app
    with TestClient(app) as c:
        yield c


# ─────────────────────────────────────────────────────────────────────
# Supabase clients (regular + service-role for admin operations)
# ─────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def supabase_url() -> str:
    url = os.getenv("SUPABASE_URL")
    if not url:
        pytest.skip("SUPABASE_URL not set — integration tests require .env.test")
    return url


@pytest.fixture(scope="session")
def supabase_anon_key() -> str:
    key = os.getenv("SUPABASE_API_KEY")
    if not key:
        pytest.skip("SUPABASE_API_KEY not set")
    return key


@pytest.fixture(scope="session")
def jwt_secret() -> str:
    secret = os.getenv("SUPABASE_JWT_SECRET")
    if not secret:
        pytest.skip("SUPABASE_JWT_SECRET not set")
    return secret


@pytest.fixture(scope="session")
def supabase_admin(supabase_url: str):
    """
    Service-role Supabase client. Used to delete test users on teardown
    and to read back persisted rows in the assess-with-consent test.
    Returns None if SUPABASE_SERVICE_ROLE_KEY isn't configured.
    """
    role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not role_key:
        return None
    from supabase import create_client
    return create_client(supabase_url, role_key)


# ─────────────────────────────────────────────────────────────────────
# Test user — real Supabase account, fresh per test
# ─────────────────────────────────────────────────────────────────────

def _gen_email() -> str:
    prefix = os.getenv("TEST_USER_EMAIL_PREFIX", "qa+coughsense")
    domain = os.getenv("TEST_USER_DOMAIN", "example.com")
    suffix = f"{int(time.time() * 1000)}-{uuid.uuid4().hex[:6]}"
    return f"{prefix}+{suffix}@{domain}"


@pytest.fixture
def test_user(client: TestClient, supabase_admin) -> Iterator[dict[str, Any]]:
    """
    Creates a real Supabase user via /api/auth/register, then logs in to get
    fresh tokens. On teardown, deletes the user via the admin client (if
    available) so the test project doesn't accumulate orphans.
    """
    email = _gen_email()
    password = os.getenv("TEST_USER_PASSWORD", "Test1234!Strong")

    reg = client.post(
        "/api/auth/register",
        json={"email": email, "password": password},
    )
    if reg.status_code != 201:
        pytest.fail(
            f"Could not create test user (status={reg.status_code}): {reg.text}\n"
            "Check that the test Supabase project has 'Confirm email' DISABLED."
        )

    body = reg.json()
    user_id = body["user"]["id"]
    access_token = body["user"].get("access_token")
    refresh_token = body["user"].get("refresh_token")

    # Some Supabase configurations don't return a session on sign-up;
    # fall back to an explicit login.
    if not access_token:
        login = client.post(
            "/api/auth/login",
            json={"email": email, "password": password},
        )
        login.raise_for_status()
        login_body = login.json()
        access_token = login_body["access_token"]
        refresh_token = login_body.get("refresh_token")

    yield {
        "id": user_id,
        "email": email,
        "password": password,
        "access_token": access_token,
        "refresh_token": refresh_token,
    }

    # Teardown
    if supabase_admin is not None:
        try:
            supabase_admin.auth.admin.delete_user(user_id)
        except Exception as e:
            # Non-fatal — the test still ran; just log the orphan
            print(f"[teardown] could not delete test user {email}: {e}")


@pytest.fixture
def auth_headers(test_user: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {test_user['access_token']}"}


# ─────────────────────────────────────────────────────────────────────
# Per-test cleanup of cough_samples + storage blobs
# ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def cleanup_cough_samples(supabase_admin, test_user):
    """
    Yields, then on teardown removes any cough_samples rows + storage blobs
    that the test created for this user. Opt-in: include this fixture in
    tests that exercise the assess-with-consent path.
    """
    yield
    if supabase_admin is None:
        return
    try:
        rows = (
            supabase_admin.table("cough_samples")
            .select("filename")
            .eq("user_id", test_user["id"])
            .execute()
        )
        filenames = [
            r["filename"] for r in (rows.data or []) if r.get("filename")
        ]
        if filenames:
            supabase_admin.storage.from_("cough-data").remove(filenames)
        supabase_admin.table("cough_samples").delete().eq(
            "user_id", test_user["id"]
        ).execute()
    except Exception as e:
        print(f"[teardown] cough_samples cleanup failed: {e}")


# ─────────────────────────────────────────────────────────────────────
# JWT helpers — for negative auth-dep tests
# ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def make_token(jwt_secret: str):
    """Returns a callable that mints an HS256 JWT with overridable claims."""
    from jose import jwt as _jwt

    def _make(
        sub: str | None = "user-abc-123",
        aud: str | None = "authenticated",
        exp: int | None = None,
        secret: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> str:
        if exp is None:
            exp = int(time.time()) + 3600
        payload: dict[str, Any] = {
            "iat": int(time.time()),
            "iss": "test",
        }
        if sub is not None:
            payload["sub"] = sub
        if aud is not None:
            payload["aud"] = aud
        if exp is not None:
            payload["exp"] = exp
        if extra:
            payload.update(extra)
        return _jwt.encode(payload, secret or jwt_secret, algorithm="HS256")

    return _make


@pytest.fixture
def expired_token(make_token) -> str:
    return make_token(exp=int(time.time()) - 60)


@pytest.fixture
def malformed_token() -> str:
    return "not.a.jwt"


@pytest.fixture
def wrong_audience_token(make_token) -> str:
    return make_token(aud="not-authenticated")


# ─────────────────────────────────────────────────────────────────────
# Markers helpers — auto-skip integration tests when env is incomplete
# ─────────────────────────────────────────────────────────────────────

def pytest_collection_modifyitems(config, items):
    if not (
        os.getenv("SUPABASE_URL")
        and os.getenv("SUPABASE_API_KEY")
        and os.getenv("SUPABASE_JWT_SECRET")
    ):
        skip_integration = pytest.mark.skip(
            reason="Integration tests require .env.test (see .env.test.example)"
        )
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip_integration)
