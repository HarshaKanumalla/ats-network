# backend/app/middleware/auth.py

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from datetime import datetime, timedelta
import jwt
import logging
from typing import Optional

from ..config import get_settings
from ..services.auth import create_tokens, verify_token
from ..services.database import validate_refresh_token

logger = logging.getLogger(__name__)
settings = get_settings()

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        try:
            # Skip auth for certain paths
            if self._should_skip_auth(request.url.path):
                return await call_next(request)

            # Get tokens from request
            access_token = self._get_access_token(request)
            refresh_token = request.cookies.get("refresh_token")

            # If no tokens present, continue without modification
            if not access_token and not refresh_token:
                return await call_next(request)

            # Verify access token
            access_token_valid = self._verify_access_token(access_token)
            
            # If access token is invalid but refresh token exists
            if not access_token_valid and refresh_token:
                new_tokens = await self._handle_token_refresh(refresh_token)
                if new_tokens:
                    response = await call_next(request)
                    self._set_token_cookies(response, new_tokens)
                    return response

            return await call_next(request)

        except Exception as e:
            logger.error(f"Auth middleware error: {str(e)}")
            return await call_next(request)

    def _should_skip_auth(self, path: str) -> bool:
        """Check if the path should skip authentication."""
        skip_paths = [
            "/auth/login",
            "/auth/register",
            "/docs",
            "/redoc",
            "/openapi.json"
        ]
        return any(path.startswith(skip_path) for skip_path in skip_paths)

    def _get_access_token(self, request: Request) -> Optional[str]:
        """Extract access token from request headers."""
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            return auth_header.split(" ")[1]
        return None

    def _verify_access_token(self, token: Optional[str]) -> bool:
        """Verify access token validity."""
        if not token:
            return False
        try:
            payload = verify_token(token)
            return bool(payload and payload.get("exp", 0) > datetime.utcnow().timestamp())
        except jwt.PyJWTError:
            return False

    async def _handle_token_refresh(self, refresh_token: str) -> Optional[dict]:
        """Handle token refresh process."""
        try:
            # Validate refresh token
            user_id = await validate_refresh_token(refresh_token)
            if not user_id:
                return None

            # Create new tokens
            access_token, new_refresh_token = create_tokens({
                "sub": user_id,
                "type": "access"
            })

            return {
                "access_token": access_token,
                "refresh_token": new_refresh_token
            }
        except Exception as e:
            logger.error(f"Token refresh error: {str(e)}")
            return None

    def _set_token_cookies(self, response: Response, tokens: dict) -> None:
        """Set token cookies in response."""
        response.set_cookie(
            key="refresh_token",
            value=tokens["refresh_token"],
            httponly=True,
            secure=settings.cookie_secure,
            domain=settings.cookie_domain,
            samesite=settings.cookie_samesite,
            max_age=settings.refresh_token_expire_days * 24 * 60 * 60
        )
        response.headers["X-New-Access-Token"] = tokens["access_token"]