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

# ----------------------------
# Response Schemas
# ----------------------------

class UserResponse(BaseModel):
    id: str
    email: EmailStr

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
        # Sign up with Supabase 
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
        # Handle common Supabase auth errors
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
        # Sign in with Supabase
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
        
        # Check for email not confirmed
        if "email not confirmed" in error_message.lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Email not confirmed. Please check Supabase settings: Authentication → Providers → Email (disable Confirm email)"
            )
        
        # Handle specific auth errors
        if "invalid" in error_message.lower() or "credentials" in error_message.lower():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )
        
        # Return the actual error for debugging
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
    """
    Get the current authenticated user's information.
    Requires a valid JWT token in the Authorization header.
    """
    try:
        # Extract user info from the JWT token
        token = credentials.credentials
        
        # Decode the token to get claims (without verification since we already verified in get_current_user)
        payload = jwt.decode(
            token,
            JWT_SECRET,
            options={"verify_signature": False, "verify_aud": False}
        )
        
        # Get email from the token claims
        email = payload.get("email")
        
        if not email:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Email not found in token"
            )
        
        return UserResponse(
            id=user_id,
            email=email
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"GET_ME ERROR: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve user information: {str(e)}"
        )
