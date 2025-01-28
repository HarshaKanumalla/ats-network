# app/routes/auth.py

from fastapi import APIRouter, Depends, HTTPException, Response, Request, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from bson import ObjectId
import logging

from ..models.user import Token, User, UserInDB
from ..core.auth import TokenManager, TokenBlacklist
from ..services.auth import authenticate_user, get_current_user
from ..services.database import get_user_by_id
from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()

@router.post("/login", response_model=Token)
async def login(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends()
) -> Token:
    """Process user login requests."""
    try:
        logger.info(f"Processing login request for user: {form_data.username}")
        
        user = await authenticate_user(form_data.username, form_data.password)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password"
            )

        token_data = {
            "sub": str(user.id),
            "email": user.email,
            "role": user.role
        }

        access_token, refresh_token = TokenManager.create_tokens(token_data)

        # Set refresh token cookie
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=settings.cookie_secure,
            samesite="lax",
            max_age=settings.refresh_token_expire_days * 24 * 60 * 60
        )

        # Convert User model to dict for response
        user_data = {
            "id": str(user.id),
            "email": user.email,
            "role": user.role,
            "full_name": user.full_name
        }

        return Token(
            access_token=access_token,
            token_type="bearer",
            user=user_data
        )

    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during login"
        )

@router.get("/me", response_model=Dict[str, Any])
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Get current user information."""
    try:
        return {
            "id": str(current_user.id),
            "email": current_user.email,
            "role": current_user.role,
            "full_name": current_user.full_name
        }
    except Exception as e:
        logger.error(f"Error retrieving current user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user information"
        )

@router.post("/refresh")
async def refresh_access_token(
    request: Request,
    response: Response
) -> Dict[str, str]:
    """Generate a new access token using refresh token."""
    try:
        refresh_token = request.cookies.get("refresh_token")
        if not refresh_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token missing"
            )

        # Verify refresh token is not blacklisted
        if await TokenBlacklist.is_blacklisted(refresh_token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token is invalid"
            )

        # Verify and decode refresh token
        payload = TokenManager.verify_token(refresh_token, settings.refresh_token_secret)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )

        # Get user data
        user = await get_user_by_id(ObjectId(payload["sub"]))
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Generate new tokens
        access_token, new_refresh_token = TokenManager.create_tokens({
            "sub": str(user.id),
            "email": user.email,
            "role": user.role
        })

        # Set new refresh token cookie
        response.set_cookie(
            key="refresh_token",
            value=new_refresh_token,
            httponly=True,
            secure=settings.cookie_secure,
            samesite=settings.cookie_samesite,
            max_age=settings.refresh_token_expire_days * 24 * 60 * 60
        )

        return {"access_token": access_token}

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Token refresh error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to refresh token"
        )

@router.post("/logout")
async def logout(response: Response) -> Dict[str, str]:
    """Handle user logout requests."""
    try:
        response.delete_cookie(
            key="refresh_token",
            httponly=True,
            samesite="lax"
        )
        logger.info("User successfully logged out")
        return {"message": "Successfully logged out"}
    except Exception as e:
        logger.error(f"Logout error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during logout"
        )

@router.get("/verify")
async def verify_session(current_user: User = Depends(get_current_user)) -> Dict[str, bool]:
    """Verify if the current session is valid."""
    return {"valid": True}