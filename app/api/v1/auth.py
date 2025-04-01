# backend/app/api/v1/auth.py

from fastapi import APIRouter, Depends, HTTPException, status, Response, File, UploadFile, Cookie, Request
from fastapi.security import OAuth2PasswordRequestForm
from typing import List, Optional, Dict, Any
import logging
from datetime import datetime
import aioredis
import secrets
from pydantic import BaseModel, EmailStr, Field

from ...core.auth.token import token_service
from ...core.auth.rate_limit import rate_limiter
from ...core.security import get_password_hash, verify_password
from ...services.user.service import user_service
from ...services.s3.service import s3_service
from ...services.email.service import email_service
from ...models.user import UserCreate, UserResponse, TokenResponse
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()

# Initialize Redis for rate limiting
redis = aioredis.from_url(
    f"redis://{settings.redis_host}:{settings.redis_port}",
    password=settings.redis_password,
    decode_responses=True
)

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str = Field(..., description="Password reset token")
    new_password: str = Field(..., min_length=8, description="New password with at least 8 characters")

class RegisterUserRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, description="Password with at least 8 characters")
    full_name: str = Field(..., max_length=100, description="Full name of the user")
    ats_name: str
    ats_address: str
    city: str
    state: str
    pin_code: str
    phone: str

@router.post("/register", response_model=UserResponse)
@rate_limiter.limit("5/minute")  # Rate limit registration attempts
async def register_user(
    user_data: RegisterUserRequest,
    documents: List[UploadFile] = File(...)
) -> UserResponse:
    """Register a new ATS center user with document verification."""
    try:
        # Validate email uniqueness
        if await user_service.get_user_by_email(user_data.email):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )

        # Validate and process documents
        if not documents or len(documents) < settings.required_document_count:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Required {settings.required_document_count} documents"
            )

        document_urls = {}
        for doc in documents:
            if not s3_service.validate_document(doc):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid document format: {doc.filename}"
                )
            url = await s3_service.upload_document(
                file=doc,
                folder=f"users/{user_data.email}/registration",
                metadata={
                    "user_email": user_data.email,
                    "document_type": doc.filename,
                    "upload_date": datetime.utcnow().isoformat()
                }
            )
            document_urls[doc.filename] = url

        hashed_password = get_password_hash(user_data.password)

        user = await user_service.create_user(
            email=user_data.email,
            password_hash=hashed_password,
            full_name=user_data.full_name,
            ats_details={
                "name": user_data.ats_name,
                "address": user_data.ats_address,
                "city": user_data.city,
                "state": user_data.state,
                "pin_code": user_data.pin_code,
                "phone": user_data.phone
            },
            documents=document_urls,
            verification_token=secrets.token_urlsafe(32)
        )

        await email_service.send_registration_pending(
            email=user.email,
            name=user.full_name,
            center_name=user_data.ats_name
        )

        logger.info(f"New user registered: {user.email}")

        return UserResponse(
            status="success",
            message="Registration successful. Pending admin verification.",
            data=user
        )

    except HTTPException as e:
        logger.warning(f"Registration failed: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed. Please try again later."
        )

@router.post("/login", response_model=TokenResponse)
@rate_limiter.limit("10/minute")  # Rate limit login attempts
async def login(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends()
) -> TokenResponse:
    """Authenticate user and provide access tokens."""
    try:
        user = await user_service.get_user_by_email(form_data.username)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials"
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is inactive"
            )

        if user.status != "approved":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account pending approval"
            )

        if not verify_password(form_data.password, user.hashed_password):
            await user_service.log_failed_login(user.id)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials"
            )

        access_token, refresh_token = await token_service.create_tokens(
            user_id=str(user.id),
            user_data={
                "role": user.role,
                "permissions": user.permissions,
                "center_id": str(user.center_id) if user.center_id else None
            }
        )

        response.set_cookie(
            key=settings.refresh_token_cookie_name,
            value=refresh_token,
            httponly=True,
            secure=settings.cookie_secure,
            samesite="lax",
            max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
            domain=settings.cookie_domain
        )

        await user_service.update_last_login(user.id)

        logger.info(f"User logged in: {user.email}")

        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            user=UserResponse(
                id=user.id,
                email=user.email,
                full_name=user.full_name,
                role=user.role,
                center_id=user.center_id,
                permissions=user.permissions
            )
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed. Please try again later."
        )

@router.post("/refresh")
async def refresh_token(request: Request, response: Response) -> Dict[str, str]:
    """Refresh access token using refresh token cookie."""
    try:
        refresh_token = request.cookies.get(settings.refresh_token_cookie_name)
        if not refresh_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="No refresh token"
            )

        new_access_token, new_refresh_token = await token_service.refresh_tokens(
            refresh_token
        )

        response.set_cookie(
            key=settings.refresh_token_cookie_name,
            value=new_refresh_token,
            httponly=True,
            secure=settings.cookie_secure,
            samesite="lax",
            max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
            domain=settings.cookie_domain
        )

        return {"access_token": new_access_token}

    except Exception as e:
        logger.error(f"Token refresh error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Failed to refresh token"
        )

@router.post("/forgot-password")
@rate_limiter.limit("3/minute")  # Strict rate limit for password reset
async def forgot_password(request: ForgotPasswordRequest) -> Dict[str, str]:
    """Initiate password reset process."""
    try:
        user = await user_service.get_user_by_email(request.email)
        if user:
            reset_token = secrets.token_urlsafe(32)
            await user_service.save_reset_token(user.id, reset_token)

            await email_service.send_password_reset(
                email=user.email,
                name=user.full_name,
                reset_token=reset_token
            )

        return {
            "message": "If an account exists with this email, "
                      "password reset instructions will be sent"
        }

    except Exception as e:
        logger.error(f"Password reset initiation error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process request"
        )

@router.post("/reset-password")
async def reset_password(request: ResetPasswordRequest) -> Dict[str, str]:
    """Reset user password with token."""
    try:
        user = await user_service.verify_reset_token(request.token)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired reset token"
            )

        hashed_password = get_password_hash(request.new_password)
        await user_service.update_password(user.id, hashed_password)

        await token_service.invalidate_all_user_tokens(str(user.id))

        return {"message": "Password reset successful"}

    except Exception as e:
        logger.error(f"Password reset error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Password reset failed"
        )