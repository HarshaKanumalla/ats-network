# backend/app/api/v1/auth.py

from fastapi import APIRouter, Depends, HTTPException, status, Response, File, UploadFile
from fastapi.security import OAuth2PasswordRequestForm
from typing import List, Optional, Dict, Any
import logging
from datetime import datetime
import aioredis
import secrets

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

@router.post("/register", response_model=UserResponse)
@rate_limiter.limit("5/minute")  # Rate limit registration attempts
async def register_user(
    user_data: UserCreate,
    documents: List[UploadFile] = File(...)
) -> UserResponse:
    """Register a new ATS center user with document verification.
    
    Args:
        user_data: Complete user registration data
        documents: Required verification documents
        
    Returns:
        Registration status and user information
        
    Raises:
        HTTPException: If registration fails or validation errors occur
    """
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

        # Upload documents to S3 with proper organization
        document_urls = {}
        for doc in documents:
            # Validate file type and size
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

        # Hash password securely
        hashed_password = get_password_hash(user_data.password)

        # Create user with pending status
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

        # Send verification email
        await email_service.send_registration_pending(
            email=user.email,
            name=user.full_name,
            center_name=user_data.ats_name
        )

        # Log successful registration
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
        # Don't expose internal errors
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
    """Authenticate user and provide access tokens.
    
    Args:
        response: FastAPI response object for setting cookies
        form_data: Login credentials
        
    Returns:
        Access token and user information
        
    Raises:
        HTTPException: If authentication fails
    """
    try:
        # Get user and verify status
        user = await user_service.get_user_by_email(form_data.username)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials"
            )

        # Check account status
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

        # Verify password
        if not verify_password(form_data.password, user.hashed_password):
            # Log failed attempt
            await user_service.log_failed_login(user.id)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials"
            )

        # Create tokens
        access_token, refresh_token = await token_service.create_tokens(
            user_id=str(user.id),
            user_data={
                "role": user.role,
                "permissions": user.permissions,
                "center_id": str(user.center_id) if user.center_id else None
            }
        )

        # Set secure refresh token cookie
        response.set_cookie(
            key=settings.refresh_token_cookie_name,
            value=refresh_token,
            httponly=True,
            secure=settings.cookie_secure,
            samesite="lax",
            max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
            domain=settings.cookie_domain
        )

        # Update last login
        await user_service.update_last_login(user.id)

        # Log successful login
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
async def refresh_token(response: Response) -> Dict[str, str]:
    """Refresh access token using refresh token cookie.
    
    Args:
        response: FastAPI response object for updating cookie
        
    Returns:
        New access token
        
    Raises:
        HTTPException: If token refresh fails
    """
    try:
        # Get refresh token from cookie
        refresh_token = request.cookies.get(settings.refresh_token_cookie_name)
        if not refresh_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="No refresh token"
            )

        # Validate and refresh tokens
        new_access_token, new_refresh_token = await token_service.refresh_tokens(
            refresh_token
        )

        # Update refresh token cookie
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

@router.post("/logout", response_model=Dict[str, str])
async def logout(
    current_user = Depends(get_current_user),
    response: Response = None,
    refresh_token: Optional[str] = Cookie(None, alias=settings.REFRESH_TOKEN_COOKIE_NAME)
) -> Dict[str, str]:
    """Logout user and invalidate all active tokens."""
    try:
        db = await get_database()
        
        # Invalidate current session
        if refresh_token:
            await token_service.invalidate_token(refresh_token)
        
        # Clear refresh token cookie
        if response:
            response.delete_cookie(
                key=settings.REFRESH_TOKEN_COOKIE_NAME,
                httponly=True,
                secure=settings.COOKIE_SECURE,
                samesite=settings.COOKIE_SAMESITE,
                domain=settings.COOKIE_DOMAIN
            )
        
        # Update user's last logout time
        await db.users.update_one(
            {"_id": ObjectId(current_user.id)},
            {
                "$set": {
                    "last_logout": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        # Invalidate all active sessions for the user
        await token_service.invalidate_all_user_tokens(str(current_user.id))
        
        # Log logout event
        await audit_service.log_activity(
            user_id=str(current_user.id),
            action="logout",
            entity_type="user",
            entity_id=str(current_user.id),
            metadata={
                "ip_address": request.client.host,
                "user_agent": request.headers.get("user-agent")
            }
        )
        
        return {
            "status": "success",
            "message": "Successfully logged out"
        }
        
    except Exception as e:
        logger.error(f"Logout error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to complete logout"
        )


@router.post("/verify-email/{token}")
async def verify_email(token: str) -> Dict[str, str]:
    """Verify user email address.
    
    Args:
        token: Email verification token
        
    Returns:
        Success message
        
    Raises:
        HTTPException: If verification fails
    """
    try:
        user = await user_service.verify_email(token)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid verification token"
            )

        return {"message": "Email verified successfully"}

    except Exception as e:
        logger.error(f"Email verification error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Verification failed"
        )

@router.post("/forgot-password")
@rate_limiter.limit("3/minute")  # Strict rate limit for password reset
async def forgot_password(email: str) -> Dict[str, str]:
    """Initiate password reset process.
    
    Args:
        email: User's email address
        
    Returns:
        Success message
        
    Raises:
        HTTPException: If process fails
    """
    try:
        user = await user_service.get_user_by_email(email)
        if user:
            # Generate and save reset token
            reset_token = secrets.token_urlsafe(32)
            await user_service.save_reset_token(user.id, reset_token)

            # Send reset email
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

@router.post("/reset-password/{token}")
async def reset_password(
    token: str,
    new_password: str
) -> Dict[str, str]:
    """Reset user password with token.
    
    Args:
        token: Password reset token
        new_password: New password
        
    Returns:
        Success message
        
    Raises:
        HTTPException: If reset fails
    """
    try:
        user = await user_service.verify_reset_token(token)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired reset token"
            )

        # Update password
        hashed_password = get_password_hash(new_password)
        await user_service.update_password(user.id, hashed_password)

        # Invalidate all existing sessions
        await token_service.invalidate_all_user_tokens(str(user.id))

        return {"message": "Password reset successful"}

    except Exception as e:
        logger.error(f"Password reset error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Password reset failed"
        )

@router.post("/token/revoke/{token_id}", response_model=Dict[str, str])
async def revoke_token(
    token_id: str,
    current_user = Depends(get_current_user),
    _=Depends(require_permission(RolePermission.MANAGE_TOKENS))
) -> Dict[str, str]:
    """Revoke specific token."""
    try:
        await token_service.revoke_token(token_id)
        
        await audit_service.log_activity(
            user_id=str(current_user.id),
            action="revoke_token",
            entity_type="token",
            entity_id=token_id,
            metadata={
                "revoked_at": datetime.utcnow().isoformat()
            }
        )
        
        return {
            "status": "success",
            "message": "Token revoked successfully"
        }
        
    except Exception as e:
        logger.error(f"Token revocation error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to revoke token"
        )

@router.post("/token/revoke-all", response_model=Dict[str, str])
async def revoke_all_tokens(
    current_user = Depends(get_current_user),
    _=Depends(require_permission(RolePermission.MANAGE_TOKENS))
) -> Dict[str, str]:
    """Revoke all active tokens for a user."""
    try:
        await token_service.invalidate_all_user_tokens(str(current_user.id))
        
        await audit_service.log_activity(
            user_id=str(current_user.id),
            action="revoke_all_tokens",
            entity_type="user",
            entity_id=str(current_user.id),
            metadata={
                "revoked_at": datetime.utcnow().isoformat()
            }
        )
        
        return {
            "status": "success",
            "message": "All tokens revoked successfully"
        }
        
    except Exception as e:
        logger.error(f"Token revocation error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to revoke tokens"
        )