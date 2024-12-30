# backend/app/routes/auth.py
from fastapi import APIRouter, Depends, HTTPException, status, Form, File, UploadFile, BackgroundTasks
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from datetime import datetime, timedelta
from typing import List, Optional
import logging

from ..models.user import (
    UserCreate, 
    UserInDB, 
    User, 
    Token, 
    TokenData,
    UserResponse,
    UserStatus,
    Role
)
from ..services.auth import (
    authenticate_user,
    create_access_token,
    get_current_user,
    get_password_hash
)
from ..services.email import (
    send_verification_email,
    send_registration_confirmation,
    send_admin_notification
)
from ..services.database import create_user, get_user_by_email
from ..config import get_settings

# System Info
SYSTEM_INFO = {
    "last_updated": "2024-12-19 18:38:58",
    "updated_by": "HarshaKanumalla"
}

# Setup logging
logger = logging.getLogger(__name__)

# Get settings
settings = get_settings()

# Create router
router = APIRouter()

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

@router.post("/register", response_model=UserResponse)
async def register_user(
    background_tasks: BackgroundTasks,
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    ats_address: str = Form(...),
    city: str = Form(...),
    district: str = Form(...),
    state: str = Form(...),
    pin_code: str = Form(...),
    files: List[UploadFile] = File(default=[])
):
    """Register a new user."""
    try:
        # Validate passwords match
        if password != confirm_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Passwords do not match"
            )

        # Check if user already exists
        existing_user = await get_user_by_email(email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )

        # Create user data with proper Role import
        user_data = {
            "full_name": full_name,
            "email": email,
            "hashed_password": get_password_hash(password),
            "ats_address": ats_address,
            "city": city,
            "district": district,
            "state": state,
            "pin_code": pin_code,
            "status": UserStatus.PENDING,
            "role": Role.USER,
            "is_active": True,
            "is_verified": False,
            "created_at": datetime.utcnow()
        }

        # Create user
        user = await create_user(user_data)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create user"
            )

        # Send emails in background
        background_tasks.add_task(send_registration_confirmation, user_data)
        background_tasks.add_task(send_admin_notification, user_data)

        return UserResponse(
            status="success",
            message="Registration successful. Please check your email for verification.",
            data=user
        )

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Registration failed: {str(e)}"
        )

@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends()
):
    """Authenticate user and return token."""
    try:
        user = await authenticate_user(form_data.username, form_data.password)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Inactive user"
            )

        if user.status != UserStatus.APPROVED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User not approved yet"
            )

        access_token_expires = timedelta(minutes=settings.jwt_expiration)
        access_token = create_access_token(
            data={
                "sub": str(user.id),
                "email": user.email,
                "role": user.role
            },
            expires_delta=access_token_expires
        )

        return Token(
            access_token=access_token,
            token_type="bearer",
            user=user
        )
    
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Login failed: {str(e)}"
        )

@router.get("/me", response_model=User)
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """Get current user information."""
    return current_user

# Export router
__all__ = ['router']