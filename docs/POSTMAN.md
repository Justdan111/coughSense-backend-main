# Postman Guide

The repo ships a complete Postman v2.1.0 collection that mirrors the
pytest integration suite. Use it for manual API exploration, demos, or
to script CI smoke tests via [Newman](https://github.com/postmanlabs/newman).

Files:
- [`tests/postman/CoughSense.postman_collection.json`](../tests/postman/CoughSense.postman_collection.json)
- [`tests/postman/CoughSense.postman_environment.json`](../tests/postman/CoughSense.postman_environment.json)

---

## Importing into Postman

1. Open Postman → **File → Import** → drop both files in.
2. In the top-right environment selector, pick **CoughSense — local**.
3. Click the eye icon next to the selector and edit:
   - `base_url` — defaults to `http://127.0.0.1:8000`
   - `email`, `password` — set to a valid account on your test Supabase
     project (or run **Auth → Register** once first)

---

## Collection structure

```
CoughSense API
├── Auth
│   ├── Health
│   ├── Register          ← run once for a brand-new account
│   ├── Login             ← stores access_token + refresh_token in env
│   ├── Refresh Token
│   ├── Get Me
│   ├── Get Account
│   └── Update Account
├── Analysis
│   ├── Analyze Cough     ← multipart, attach a WAV in Body → form-data
│   ├── Assess Risk (low risk example)
│   └── Assess Risk (high risk: blood)
└── Negative cases
    ├── Get Me — no token (401/403)
    ├── Login — wrong password (401)
    ├── Register — invalid email (422)
    └── Update Account — empty name (422)
```

Every request has a `pm.test(...)` block asserting status code and key
response fields, so the **Runner** turns the collection into a smoke
test suite.

---

## Auto-login

The collection's **pre-request** script checks `{{access_token}}` before
each request. If empty, it calls `POST /api/auth/login` with the env's
`{{email}}` and `{{password}}`, then writes the new token back to the
environment. So you can fire any protected request directly without
manually chaining Login first.

The script is at the **collection** level — disable it from the
collection's Settings tab if you want full manual control.

---

## Running with Newman (CI-ready)

```bash
# Install Newman once
npm install -g newman

# Run the whole collection
newman run \
  tests/postman/CoughSense.postman_collection.json \
  -e tests/postman/CoughSense.postman_environment.json \
  --env-var email="qa+coughsense@example.com" \
  --env-var password="$TEST_USER_PASSWORD"

# CI-friendly: HTML report + non-zero exit on failure
newman run tests/postman/CoughSense.postman_collection.json \
  -e tests/postman/CoughSense.postman_environment.json \
  -r cli,htmlextra \
  --reporter-htmlextra-export newman-report.html
```

---

## Uploading audio in **Analyze Cough**

Form-data file uploads can't be embedded in JSON, so the file path is
**not** stored in the collection. To run the request:

1. Open **Analysis → Analyze Cough**.
2. Go to **Body → form-data**.
3. The row labeled `audio` shows type `File` — click **Select Files**
   and pick a WAV file (e.g. one of the synthesized fixtures at
   `tests/fixtures/audio/synthetic_cough.wav` or your own
   `cough_clear.wav`).
4. Hit **Send**.

When run via Newman, point at a file with `--folder Analysis` and use
`--global-var audio=path/to/cough_clear.wav` plus a small wrapper
script — or just leave the audio test for the pytest suite, which
handles file uploads natively.

---

## Pairing with pytest

Pytest is the source of truth for correctness — the Postman collection is
a thinner UX layer over the same endpoints. If a test fails in pytest,
it should fail in Postman; if you add a new endpoint:

1. Add the pytest case in `tests/integration/`.
2. Add the corresponding request in the Postman collection (copy the
   structure of an existing one, including the `pm.test` block).
3. Run both — pytest first, then Newman against a running dev server.
