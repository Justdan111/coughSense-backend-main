# CoughSense API Reference

Base URL (local): `http://127.0.0.1:8000`
Live OpenAPI/Swagger: `/docs` · ReDoc: `/redoc`

All endpoints below are mounted under the `/api` prefix
(see [`app/main.py:15-16`](../app/main.py#L15-L16)).

## Conventions

- **Auth**: protected endpoints require `Authorization: Bearer <access_token>`
  obtained from `POST /api/auth/login`.
- **Errors**: error responses use FastAPI's standard `{ "detail": "..." }` shape.
  Validation errors return `422` with a list of field-level errors.

## Endpoint catalog

| Method | Path                       | Auth | Purpose                                          | Source |
|--------|----------------------------|------|--------------------------------------------------|--------|
| GET    | `/api/auth/health`         | no   | Liveness check                                    | [`app/api/auth.py:73`](../app/api/auth.py#L73) |
| POST   | `/api/auth/register`       | no   | Create a new user account                         | [`app/api/auth.py:82`](../app/api/auth.py#L82) |
| POST   | `/api/auth/login`          | no   | Sign in, return access + refresh token            | [`app/api/auth.py:133`](../app/api/auth.py#L133) |
| POST   | `/api/auth/refresh`        | no   | Exchange a refresh token for a new access token   | [`app/api/auth.py:186`](../app/api/auth.py#L186) |
| GET    | `/api/auth/me`             | yes  | Return id + email of authenticated user           | [`app/api/auth.py:225`](../app/api/auth.py#L225) |
| GET    | `/api/auth/account`        | yes  | Return id + email + display name                  | [`app/api/auth.py:264`](../app/api/auth.py#L264) |
| PATCH  | `/api/auth/account`        | yes  | Set/update display name (upsert)                  | [`app/api/auth.py:315`](../app/api/auth.py#L315) |
| POST   | `/api/analysis/analyze`    | yes  | Audio → cough confidence (multipart upload)       | [`app/api/analysis.py:128`](../app/api/analysis.py#L128) |
| POST   | `/api/analysis/assess`     | yes  | Confidence + symptoms → triage result             | [`app/api/analysis.py:192`](../app/api/analysis.py#L192) |

---

## Auth

### `POST /api/auth/register`

Creates a new Supabase user. Email confirmation must be **disabled** in
the Supabase dashboard for the response to include a usable session.

**Request body**
```json
{ "email": "user@example.com", "password": "min-8-chars" }
```

**Validation**
- `email` — must be a valid email (`pydantic.EmailStr`)
- `password` — minimum 8, maximum 128 characters

**Responses**
- `201 Created`
  ```json
  {
    "message": "Registration successful. You can now login.",
    "user": {
      "id": "uuid",
      "email": "user@example.com",
      "access_token": "eyJ...",
      "token_type": "bearer",
      "refresh_token": "v1:..."
    }
  }
  ```
- `400 Bad Request` — `Email already registered` or other Supabase-side rejections
- `422 Unprocessable Entity` — bad email or short password

### `POST /api/auth/login`

**Request body** — same shape as register (`email`, `password`).

**Responses**
- `200 OK`
  ```json
  {
    "access_token": "eyJ...",
    "token_type": "bearer",
    "user": { "id": "uuid", "email": "user@example.com" }
  }
  ```
- `401 Unauthorized` — invalid credentials
- `403 Forbidden` — email not confirmed (when Supabase has confirmation enabled)

### `POST /api/auth/refresh`

**Request body**
```json
{ "refresh_token": "v1:..." }
```

**Responses**
- `200 OK` — `{ "access_token": "...", "refresh_token": "...", "token_type": "bearer" }`
- `401 Unauthorized` — refresh token invalid/expired

### `GET /api/auth/me` _(auth)_

**Response — `200 OK`**
```json
{ "id": "uuid", "email": "user@example.com" }
```

### `GET /api/auth/account` _(auth)_

Returns the user plus their display name from the `profiles` table.
`name` is `null` if the user has never set one.

**Response — `200 OK`**
```json
{ "id": "uuid", "email": "user@example.com", "name": "Dan Emmanuel" }
```

### `PATCH /api/auth/account` _(auth)_

Upserts the display name in the `profiles` table.

**Request body**
```json
{ "name": "Dan Emmanuel" }
```
- `name` — required, 1-100 chars; the value is `.strip()`-ed server-side.

**Responses**
- `200 OK` — same shape as `GET /api/auth/account`
- `422` — empty or oversized name

---

## Analysis

### `POST /api/analysis/analyze` _(auth)_

Multipart upload of a cough recording.

**Form data**
- `audio` — file part. Allowed MIME types:
  `audio/wav`, `audio/mpeg`, `audio/mp3`, `audio/ogg`, `audio/flac`,
  `audio/x-wav`, `audio/x-m4a`.

**Server-side validation** (see [`app/ml/validator.py`](../app/ml/validator.py))
- duration ≥ 2s
- RMS loudness ≥ 0.01
- spectral flatness ≤ 0.5 (rejects pure noise)
- 500-4000Hz energy ratio ≥ 0.2 (rejects non-cough audio)

After validation, runs YAMNet → Random Forest. The classifier's cough
probability is returned. If it is `< 0.25` the request is rejected.

**Responses**
- `200 OK`
  ```json
  {
    "user_id": "uuid",
    "cough_confidence": 0.82,
    "cough_confidence_pct": 82.0,
    "disclaimer": "This result is for triage purposes only..."
  }
  ```
- `400 Bad Request` — invalid MIME, audio fails validation, or confidence < 0.25
- `401 / 403` — missing or invalid bearer token

### `POST /api/analysis/assess` _(auth)_

Combines a cough confidence score with symptom answers and returns a
triage recommendation.

**Request body**
```json
{
  "cough_confidence": 0.82,
  "fever": false,
  "blood": false,
  "chest_pain": true,
  "difficulty_breathing": false,
  "save_for_training": true
}
```

**Scoring** (see [`app/ml/inference.py:60`](../app/ml/inference.py#L60))

| Component             | Points |
|-----------------------|-------:|
| `cough_confidence ≥ 0.7` | 3 |
| `0.4 ≤ confidence < 0.7` | 2 |
| `confidence < 0.4`       | 1 |
| `blood`                  | 4 |
| `chest_pain`             | 2 |
| `difficulty_breathing`   | 2 |
| `fever`                  | 1 |

`score >= 4 → "risky"`, otherwise `"less_risky"`.

**Side effect** — when `save_for_training=true`, the original audio is
uploaded to the `cough-data` Supabase bucket and a row is inserted into
`cough_samples`. This is a fire-and-forget; storage failures do not
break the response.

**Response — `200 OK`**
```json
{
  "user_id": "uuid",
  "result": "risky",
  "cough_confidence_pct": 82.0,
  "score": 5,
  "summary": "Your cough pattern and symptoms suggest a higher respiratory risk.",
  "recommendation": "Please seek medical attention soon.",
  "actions": ["Visit a clinic...", "Avoid close contact...", "Monitor for...", "Do not ignore..."],
  "disclaimer": "This result is for triage purposes only..."
}
```

---

## Database schema (Supabase)

Two tables under the public schema:

```sql
profiles (
  user_id uuid primary key references auth.users(id),
  name    text
);

cough_samples (
  id                  bigint primary key generated by default as identity,
  user_id             uuid not null references auth.users(id),
  filename            text not null,
  cough_confidence    numeric(5,2),     -- percentage, 0-100
  fever               boolean default false,
  blood               boolean default false,
  chest_pain          boolean default false,
  difficulty_breathing boolean default false,
  result              text,             -- 'risky' | 'less_risky'
  score               int,
  consent             boolean default true,
  created_at          timestamptz default now()
);
```

Storage bucket: `cough-data` (public; uploaded WAVs keyed by `<uuid>_<original-name>`).
