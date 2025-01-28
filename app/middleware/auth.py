"""Authentication middleware for request processing."""
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from datetime import datetime
import logging
from typing import Optional, Dict

from ..config import get_settings
from ..core.auth import TokenManager
from ..services.database import validate_refresh_token

logger = logging.getLogger(__name__)
settings = get_settings()

class AuthMiddleware(BaseHTTPMiddleware):
    """Handles authentication for incoming requests."""

    async def dispatch(self, request: Request, call_next) -> Response:
        """Process each request for authentication."""
        try:
            if await self._should_skip_auth(request.url.path):
                return await call_next(request)

            access_token = await self._get_access_token(request)
            refresh_token = request.cookies.get("refresh_token")

            if not access_token and not refresh_token:
                return await call_next(request)

            access_token_valid = await self._verify_access_token(access_token)
            
            if not access_token_valid and refresh_token:
                new_tokens = await self._handle_token_refresh(refresh_token)
                if new_tokens:
                    response = await call_next(request)
                    await self._set_token_cookies(response, new_tokens)
                    return response

            return await call_next(request)

        except Exception as e:
            logger.error(f"Auth middleware error: {str(e)}")
            return await call_next(request)

    async def _should_skip_auth(self, path: str) -> bool:
        """Determine if authentication should be skipped for this path."""
        skip_paths = {
            "/auth/login",
            "/auth/register",
            "/docs",
            "/redoc",
            "/openapi.json"
        }
        return any(path.startswith(skip_path) for skip_path in skip_paths)

    async def _get_access_token(self, request: Request) -> Optional[str]:
        """Extract access token from request headers."""
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            return auth_header.split(" ")[1]
        return None

    async def _verify_access_token(self, token: Optional[str]) -> bool:
        """Verify access token validity."""
        if not token:
            return False
        
        payload = TokenManager.verify_token(token, settings.access_token_secret)
        return bool(payload and payload.get("exp", 0) > datetime.utcnow().timestamp())

    async def _handle_token_refresh(self, refresh_token: str) -> Optional[Dict[str, str]]:
        """Handle token refresh process."""
        try:
            user_id = await validate_refresh_token(refresh_token)
            if not user_id:
                return None

            new_tokens = TokenManager.create_tokens({
                "sub": user_id,
                "type": "access"
            })

            return {
                "access_token": new_tokens[0],
                "refresh_token": new_tokens[1]
            }
        except Exception as e:
            logger.error(f"Token refresh error: {str(e)}")
            return None

    async def _set_token_cookies(self, response: Response, tokens: Dict[str, str]) -> None:
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