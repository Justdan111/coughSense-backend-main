# CoughSense API Backend

FastAPI backend for CoughSense - a cough analysis and triage system.

## Setup

### 1. Install Dependencies

```bash
uv sync
```

### 2. Configure Environment Variables

Copy the example environment file and fill in your Supabase credentials:

```bash
cp .env.example .env
```

Edit `.env` with your Supabase credentials:

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_API_KEY=your-anon-key
SUPABASE_JWT_SECRET=your-jwt-secret
```

#### Getting Supabase Credentials:

1. Go to your [Supabase Dashboard](https://supabase.com/dashboard)
2. Select your project
3. Go to **Settings** → **API**
4. Copy:
   - **Project URL** → `SUPABASE_URL`
   - **anon public** key → `SUPABASE_API_KEY`
   - **JWT Secret** → `SUPABASE_JWT_SECRET`

### 3. Run the Development Server

```bash
uv run uvicorn app.main:app --reload

```

The API will be available at `http://127.0.0.1:8000`

## API Documentation

Once running, visit:
- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

## Authentication

The API uses Supabase Auth with JWT tokens.

### Register a new user:
```bash
POST /api/auth/register
{
  "email": "user@example.com",
  "password": "your-password"
}
```

### Login:
```bash
POST /api/auth/login
{
  "email": "user@example.com",
  "password": "your-password"
}
```

Returns:
```json
{
  "access_token": "eyJhbG...",
  "token_type": "bearer",
  "user": {
    "id": "user-uuid",
    "email": "user@example.com"
  }
}
```

### Using Protected Endpoints:

Include the token in the Authorization header:
```
Authorization: Bearer eyJhbG...
```

### Analyze Cough (Protected):
```bash
POST /api/analysis/analyze
Authorization: Bearer your-token
Content-Type: multipart/form-data

audio: <audio-file.wav>
```

## Project Structure

```
app/
├── api/                 # API routes
│   ├── auth.py         # Authentication endpoints
│   └── analysis.py     # Cough analysis endpoints
├── core/               # Core configuration
│   └── config.py       # Supabase client & env vars
├── deps/               # Dependencies
│   └── auth.py         # JWT verification dependency
├── ml/                 # Machine learning
│   ├── inference.py    # Model inference
│   └── yamnet_model.py # YAMNet embeddings
├── utils/              # Utilities
│   └── audio.py        # Audio file handling
└── main.py             # FastAPI app entry point
```

## Security Notes

1. **JWT Verification**: Tokens are verified using the Supabase JWT secret
2. **Audience Check**: Tokens must have `"aud": "authenticated"`
3. **Protected Routes**: Use `Depends(get_current_user)` to protect endpoints
4. **Never trust `getSession()` on server**: Always use JWT verification

## Development

- Python 3.11+ required
- Uses `uv` for dependency management
- FastAPI for the web framework
- Supabase for authentication and database