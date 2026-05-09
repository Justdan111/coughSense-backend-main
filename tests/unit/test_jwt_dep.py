"""
Unit tests for app.deps.auth.get_current_user.

These tests need the real JWT secret (so HS256 verification works) and
exercise every branch in the dependency. They don't hit Supabase.

⚠️  SECURITY OBSERVATION
The implementation in app/deps/auth.py has a deliberately permissive
fallback: when the strict HS256 + audience-checked decode fails with a
JWTError, it RETRIES with `verify_signature=False, verify_aud=False` and
accepts the result if it has a `sub` claim. That means:

    - tokens signed with the WRONG secret are accepted
    - tokens with the WRONG audience are accepted
    - only EXPIRED, MALFORMED, or SUB-LESS tokens are rejected

The tests below document this current behavior. The assertions marked
"PERMISSIVE FALLBACK" should arguably fail (i.e. those tokens should be
rejected), and those tests will need to be flipped if/when the fallback
is tightened to fix the issue.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.deps.auth import get_current_user


def _creds(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


# ─────────────────────────────────────────────────────────────────────
# Happy path
# ─────────────────────────────────────────────────────────────────────

def test_valid_token_returns_user_id(make_token):
    token = make_token(sub="user-xyz")
    user_id = get_current_user(_creds(token))
    assert user_id == "user-xyz"


# ─────────────────────────────────────────────────────────────────────
# Rejected — these all hit failure branches in BOTH decode paths
# ─────────────────────────────────────────────────────────────────────

def test_expired_token_rejected(expired_token):
    with pytest.raises(HTTPException) as exc:
        get_current_user(_creds(expired_token))
    assert exc.value.status_code == 401


def test_malformed_token_rejected(malformed_token):
    with pytest.raises(HTTPException) as exc:
        get_current_user(_creds(malformed_token))
    assert exc.value.status_code == 401


def test_token_missing_sub_rejected(make_token):
    """Token decodes successfully but has no `sub` claim → 401."""
    token = make_token(sub=None)
    with pytest.raises(HTTPException) as exc:
        get_current_user(_creds(token))
    assert exc.value.status_code == 401
    assert "user ID" in exc.value.detail


def test_empty_bearer_rejected():
    with pytest.raises(HTTPException) as exc:
        get_current_user(_creds(""))
    assert exc.value.status_code == 401


# ─────────────────────────────────────────────────────────────────────
# PERMISSIVE FALLBACK — current behavior, arguably a security bug
# ─────────────────────────────────────────────────────────────────────

def test_wrong_audience_currently_accepted(make_token):
    """
    PERMISSIVE FALLBACK: a token whose `aud` ≠ "authenticated" should be
    rejected, but the second decode skips audience verification, so it
    is accepted today.
    """
    token = make_token(sub="user-xyz", aud="not-authenticated")
    user_id = get_current_user(_creds(token))
    assert user_id == "user-xyz"


def test_wrong_secret_currently_accepted(make_token):
    """
    PERMISSIVE FALLBACK: a token signed with a different secret should be
    rejected, but the second decode skips signature verification.
    """
    token = make_token(sub="user-xyz", secret="not-the-real-secret")
    user_id = get_current_user(_creds(token))
    assert user_id == "user-xyz"
