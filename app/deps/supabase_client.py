"""
Per-request Supabase client with the user's JWT attached.

The global client in app/core/config.py uses only the anon key, so PostgREST
sees those requests as the `anon` role and `auth.uid()` returns NULL. That
makes any per-user RLS policy on `profiles` / `cough_samples` impossible to
satisfy.

This dependency builds a fresh client per request and forwards the user's
Bearer token to PostgREST + Storage. Now `auth.uid()` resolves to the
authenticated user and the standard "rows where user_id = auth.uid()"
policies work as expected.

Use it as:
    db: Client = Depends(get_user_supabase)
"""
from __future__ import annotations

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase import Client, create_client

from app.core.config import SUPABASE_API_KEY, SUPABASE_URL

_security = HTTPBearer()


def get_user_supabase(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
) -> Client:
    client = create_client(SUPABASE_URL, SUPABASE_API_KEY)
    client.postgrest.auth(credentials.credentials)
    # Storage uploads also need the JWT so RLS storage policies see the user.
    try:
        client.storage._client.headers["Authorization"] = (
            f"Bearer {credentials.credentials}"
        )
    except Exception:
        # Different supabase-py versions expose storage internals differently;
        # fall back gracefully — uploads will use the anon key.
        pass
    return client
