# backend/app/routes/auth.py

from fastapi import APIRouter, Depends, HTTPException, status, Response, Request, Cookie
from fastapi.security import OAuth2PasswordRequestForm
from datetime import datetime, timedelta
import logging

from ..models.user import User, Token, UserCreate, UserResponse
from ..core.security import get_password_hash
from ..services.auth import (
    authenticate_user,
    create_tokens,
    set_refresh_token_cookie,
    verify_token
)
from ..services.database import (
    store_refresh_token,
    invalidate_refresh_token,
    invalidate_user_refresh_tokens,
    get_user_by_email
)
from ..services.email import (
    send_verification_email,
    send_registration_confirmation,
    send_admin_notification
)
from ..config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/auth",
    tags=["authentication"],
    responses={404: {"description": "Not found"}}
)

@router.get("/test")
async def test_auth():
    """Test endpoint to verify router functionality."""
    logger.info("Auth test endpoint accessed")
    return {"status": "success", "message": "Auth router is working correctly"}

@router.post("/login", response_model=Token)
async def login(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends()
):
    """Handle user login and token generation."""
    logger.info(f"Processing login request from: {request.client.host}")
    logger.info(f"Login attempt for username: {form_data.username}")

    try:
        # Authenticate user
        user = await authenticate_user(form_data.username, form_data.password)
        if not user:
            logger.warning(f"Authentication failed for user: {form_data.username}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Create tokens
        user_data = {
            "id": str(user.id),
            "email": user.email,
            "role": user.role
        }
        access_token, refresh_token = create_tokens(user_data)

        # Store refresh token
        await store_refresh_token(
            str(user.id),
            refresh_token,
            datetime.utcnow() + timedelta(days=settings.refresh_token_expire_days)
        )

        # Set refresh token cookie
        set_refresh_token_cookie(response, refresh_token)

        logger.info(f"Login successful for user: {form_data.username}")
        return Token(
            access_token=access_token,
            token_type="bearer",
            user=user
        )

    except HTTPException as he:
        logger.error(f"HTTP Exception during login: {str(he)}")
        raise he
    except Exception as e:
        logger.error(f"Login error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.post("/logout")
async def logout(
    response: Response,
    request: Request,
    refresh_token: str = Cookie(None, alias="refresh_token")
):
    """Handle user logout."""
    logger.info("Processing logout request")
    try:
        if refresh_token:
            await invalidate_refresh_token(refresh_token)
        response.delete_cookie("refresh_token")
        logger.info("Logout successful")
        return {"message": "Successfully logged out"}
    except Exception as e:
        logger.error(f"Logout error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Logout failed"
        )

@router.post("/register", response_model=UserResponse)
async def register(user_create: UserCreate):
    """Handle user registration."""
    logger.info(f"Processing registration request for email: {user_create.email}")

    try:
        # Check if user exists
        existing_user = await get_user_by_email(user_create.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )

        # Create user
        hashed_password = get_password_hash(user_create.password)
        user_data = user_create.dict(exclude={'password', 'confirm_password'})
        user_data['hashed_password'] = hashed_password

        user = await create_user(user_data)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create user"
            )

        logger.info(f"Registration successful for user: {user.email}")
        return UserResponse(
            status="success",
            message="Registration successful. Please check your email for verification.",
            data=user
        )

    except HTTPException as he:
        logger.error(f"Registration HTTP error: {str(he)}")
        raise he
    except Exception as e:
        logger.error(f"Registration error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )