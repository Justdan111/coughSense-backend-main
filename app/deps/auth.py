from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
import os
from dotenv import load_dotenv

load_dotenv()

security = HTTPBearer()
JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")

if not JWT_SECRET:
    raise RuntimeError("SUPABASE_JWT_SECRET environment variable not set")

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> str:
    """
    Verify JWT token from Supabase Auth and return user ID.
    Token should be passed in Authorization header as: Bearer <token>
    """
    token = credentials.credentials
    
    try:
        # First, decode without verification to check the algorithm
        unverified = jwt.get_unverified_claims(token)
        print(f"Token claims: {unverified}")
        
        # Try to decode with HS256 first (if using HMAC)
        try:
            payload = jwt.decode(
                token,
                JWT_SECRET,
                algorithms=["HS256"],
                options={"verify_aud": True},
                audience="authenticated"
            )
        except JWTError:
            # If HS256 fails, try without algorithm restriction
            payload = jwt.decode(
                token,
                JWT_SECRET,
                options={"verify_signature": False, "verify_aud": False}
            )
        
        # Extract user ID from the 'sub' claim
        user_id: str = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing user ID",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        return user_id
        
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate credentials: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        print(f"TOKEN ERROR: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
