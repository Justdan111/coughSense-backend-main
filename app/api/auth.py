from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, Field
from app.core.config import supabase
from app.deps.auth import get_current_user
from jose import jwt
import os
from dotenv import load_dotenv

load_dotenv()
JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")

router = APIRouter(prefix="/auth", tags=["Auth"])


# ----------------------------
# Request Schemas
# ----------------------------

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(
        min_length=8,
        max_length=128,
        description="Password must be at least 8 characters"
    )

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class UpdateAccountRequest(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=100,
        description="User's display name"
    )


# ----------------------------
# Response Schemas
# ----------------------------

class UserResponse(BaseModel):
    id: str
    email: EmailStr

class AccountResponse(BaseModel):
    id: str
    email: EmailStr
    name: str | None = None

class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# ----------------------------
# Health Check
# ----------------------------

@router.get("/health")
def auth_health():
    return {"status": "auth ok"}


# ----------------------------
# Register
# ----------------------------

@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED
)
def register(data: RegisterRequest):
    try:
        res = supabase.auth.sign_up({
            "email": data.email,
            "password": data.password,
            "options": {
                "email_redirect_to": None,
                "data": {}
            }
        })

        if not res.user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Registration failed. Please try again."
            )

        return {
            "message": "Registration successful. You can now login.",
            "user": {
                "id": res.user.id,
                "email": res.user.email,
                "access_token": res.session.access_token if res.session else None,
                "token_type": "bearer" if res.session else None,
                "refresh_token": res.session.refresh_token if res.session else None
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        error_message = str(e)
        if "already registered" in error_message.lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Registration failed: {error_message}"
        )


# ----------------------------
# Login
# ----------------------------

@router.post(
    "/login",
    response_model=AuthResponse
)
def login(data: LoginRequest):
    try:
        res = supabase.auth.sign_in_with_password({
            "email": data.email,
            "password": data.password
        })

        if not res.session or not res.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )

        return AuthResponse(
            access_token=res.session.access_token,
            user=UserResponse(
                id=res.user.id,
                email=res.user.email
            )
        )

    except HTTPException:
        raise
    except Exception as e:
        error_message = str(e)
        print(f"LOGIN ERROR: {error_message}")

        if "email not confirmed" in error_message.lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Email not confirmed. Please check Supabase settings: Authentication → Providers → Email (disable Confirm email)"
            )

        if "invalid" in error_message.lower() or "credentials" in error_message.lower():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {error_message}"
        )


# ----------------------------
# Get Current User
# ----------------------------

@router.get(
    "/me",
    response_model=UserResponse
)
def get_me(
    user_id: str = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())
):
    try:
        token = credentials.credentials
        payload = jwt.decode(
            token,
            JWT_SECRET,
            options={"verify_signature": False, "verify_aud": False}
        )
        email = payload.get("email")

        if not email:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Email not found in token"
            )

        return UserResponse(id=user_id, email=email)

    except HTTPException:
        raise
    except Exception as e:
        print(f"GET_ME ERROR: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve user information: {str(e)}"
        )


# ----------------------------
# Get Account (name + email)
# ----------------------------

@router.get(
    "/account",
    response_model=AccountResponse
)
def get_account(
    user_id: str = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())
):
    """
    Returns the current user's email and saved display name.
    """
    try:
        token = credentials.credentials
        payload = jwt.decode(
            token,
            JWT_SECRET,
            options={"verify_signature": False, "verify_aud": False}
        )
        email = payload.get("email")

        # Fetch name from profiles table
        result = supabase.table("profiles") \
            .select("name") \
            .eq("user_id", user_id) \
            .single() \
            .execute()

        name = result.data.get("name") if result.data else None

        return AccountResponse(id=user_id, email=email, name=name)

    except HTTPException:
        raise
    except Exception as e:
        print(f"GET_ACCOUNT ERROR: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve account information: {str(e)}"
        )


# ----------------------------
# Update Account (save name)
# ----------------------------

@router.patch(
    "/account",
    response_model=AccountResponse
)
def update_account(
    data: UpdateAccountRequest,
    user_id: str = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())
):
    """
    Save or update the user's display name.
    Uses upsert so it works whether the profile row exists or not.
    """
    try:
        token = credentials.credentials
        payload = jwt.decode(
            token,
            JWT_SECRET,
            options={"verify_signature": False, "verify_aud": False}
        )
        email = payload.get("email")

        # Upsert into profiles table
        supabase.table("profiles").upsert({
            "user_id": user_id,
            "name": data.name.strip()
        }).execute()

        return AccountResponse(id=user_id, email=email, name=data.name.strip())

    except HTTPException:
        raise
    except Exception as e:
        print(f"UPDATE_ACCOUNT ERROR: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update account: {str(e)}"
        )