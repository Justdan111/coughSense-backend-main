# Testing Guide

The CoughSense backend uses **pytest** with two tiers: fast unit tests
that run hermetically, and integration tests that hit a real Supabase
test project. The Postman collection at
[`tests/postman/CoughSense.postman_collection.json`](../tests/postman/CoughSense.postman_collection.json)
mirrors the integration tests for manual / CI exploration.

---

## Prerequisites

1. **Install dev dependencies**
   ```bash
   cd backend
   uv sync --group dev
   ```

2. **Create a dedicated Supabase test project**
   The integration suite registers, logs in, and (when configured) deletes
   real users. **Do not point it at your production Supabase project.**

   In the test project:
   - Go to **Authentication → Providers → Email** → uncheck **Confirm email**
     (otherwise `register → login` fails because the user can't sign in until
     they click an email link).
   - Open the **SQL Editor**, paste the contents of
     [`db/migrations.sql`](../db/migrations.sql), and run it. That creates the
     `profiles` and `cough_samples` tables, the `cough-data` storage bucket,
     and the RLS policies the backend's authenticated PostgREST calls need.

   > Skipping the migration step is the most common source of the
   > `42501: new row violates row-level security policy for table "profiles"`
   > error in `test_account_patch_then_get`.

3. **Configure `.env.test`**
   ```bash
   cp .env.test.example .env.test
   # Fill in SUPABASE_URL, SUPABASE_API_KEY, SUPABASE_JWT_SECRET
   # Optionally fill in SUPABASE_SERVICE_ROLE_KEY for automatic user cleanup
   ```

4. **(Optional) Provide a real cough recording**
   Drop a 3-5 second WAV at `tests/fixtures/audio/cough_clear.wav`. Without
   it, the ML happy-path tests are **skipped**, not failed. See
   [`tests/fixtures/audio/README.md`](../tests/fixtures/audio/README.md).

---

## Running the suite

### Fast loop (no network, no model)
```bash
uv run pytest -m "not integration" -q
```

### Integration only
```bash
uv run pytest -m integration
```

### Everything + coverage report
```bash
uv run pytest --cov=app --cov-report=term-missing
```

### A single test
```bash
uv run pytest tests/unit/test_calculate_risk.py::test_calculate_risk_threshold_is_inclusive_at_4 -vv
```

### Watch mode (re-run on file change)
```bash
uv run pytest --looponfail   # requires pytest-xdist; install ad-hoc if you want it
```

---

## Layout

```
tests/
├── conftest.py                  # Shared fixtures (client, test_user, JWT helpers, ...)
├── fixtures/
│   ├── audio_factory.py         # Synthesizes the WAV fixtures at session start
│   └── audio/                   # Generated WAVs + (optional) cough_clear.wav
├── unit/                        # No network, no model where possible
│   ├── test_calculate_risk.py
│   ├── test_validate_audio.py
│   ├── test_triage_guidance.py
│   └── test_jwt_dep.py
├── integration/                 # @pytest.mark.integration — hits real Supabase
│   ├── test_auth_flow.py
│   ├── test_analysis_flow.py    # also @pytest.mark.ml
│   └── test_cors.py
└── postman/
    ├── CoughSense.postman_collection.json
    └── CoughSense.postman_environment.json
```

---

## Key fixtures

| Fixture                  | Scope     | What it does |
|--------------------------|-----------|--------------|
| `client`                 | session   | `TestClient(app)` wrapping the FastAPI app |
| `test_user`              | function  | Creates a fresh Supabase user; tears down via service role |
| `auth_headers`           | function  | `{"Authorization": f"Bearer {access_token}"}` for `test_user` |
| `make_token(...)`        | function  | Mints HS256 JWTs with overridable `sub`/`aud`/`exp`/secret |
| `expired_token`          | function  | A token whose `exp` is in the past |
| `wrong_audience_token`   | function  | A token whose `aud` is not `authenticated` |
| `malformed_token`        | function  | The literal string `"not.a.jwt"` |
| `audio_fixture(name)`    | function  | Returns `(filename, bytes, mime)` ready for `client.post(..., files=...)` |
| `supabase_admin`         | session   | Service-role Supabase client (or `None` if key not configured) |
| `cleanup_cough_samples`  | function  | Opt-in teardown that deletes rows + storage blobs created by a test |

---

## Adding a new endpoint test

1. Decide the tier:
   - Pure logic (no I/O)? → `tests/unit/`, no marker.
   - Hits Supabase Auth/DB/Storage? → `tests/integration/`, mark with
     `@pytest.mark.integration` (use `pytest.mark.ml` too if it loads
     YAMNet).
2. Use the existing `client` and `auth_headers` fixtures rather than
   building them by hand.
3. If your test creates a row in `cough_samples`, add the
   `cleanup_cough_samples` fixture to its arguments.
4. For negative auth tests, prefer the `make_token` fixture over
   hand-crafting tokens.
5. Mirror the test in
   [`tests/postman/CoughSense.postman_collection.json`](../tests/postman/CoughSense.postman_collection.json)
   if it covers a new endpoint.

---

## Troubleshooting

**`pytest.skip("SUPABASE_URL not set ...")`**
Your `.env.test` is missing or doesn't define one of the three required
Supabase variables. The collection-time hook in `conftest.py` skips all
integration tests in that case.

**`Could not create test user (status=400): ... Email not confirmed`**
Disable email confirmation on the test Supabase project. See
[Prerequisites](#prerequisites) step 2.

**`could not delete test user qa+coughsense+...@example.com`**
You didn't set `SUPABASE_SERVICE_ROLE_KEY`. The test still passed —
it just leaves an orphan user in the test project. Either set the key
or periodically purge users matching the `qa+coughsense` prefix from
the Supabase dashboard.

**`FileNotFoundError: app/models/yamnet_random_forest.joblib`**
The classifier file is required at import time of `app/ml/inference.py`.
It's checked into the repo at `app/models/`. If you get this error,
either you cloned without LFS or the file is missing — restore it.

**`tensorflow` import takes ~10s on first run**
That's the YAMNet model loading. It's lazy, so unit tests that don't
import `app.ml.inference` skip the cost. The session-scoped `client`
fixture imports it indirectly via `app.api.analysis`, so the cost is
paid once per session.

**Tests pass locally but fail in CI**
Most likely your CI doesn't have the trained model files or the test
Supabase credentials. The model files (`yamnet_random_forest.joblib`,
`yamnet_mean.npy`) live under `app/models/` — make sure they're either
committed (Git LFS) or fetched at CI startup.

---

## Coverage targets

The current suite aims for **≥ 85% line coverage** across:
- `app/api/`     (routers)
- `app/ml/`      (inference + validator)
- `app/deps/`    (auth dependency)
- `app/core/`    (config — mostly covered by import-time validation)

`app/ml/yamnet_model.py` is excluded from coverage because it's a thin
wrapper around a TensorFlow Hub download that we don't want to exercise
in tests.
