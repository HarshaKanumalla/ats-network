# backend/app/core/auth/middleware.py

from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Callable, Dict, Any
import logging
from datetime import datetime, timedelta
import jwt
import redis
import ipaddress
from urllib.parse import urlparse

from ...core.security import security_manager
from ...core.exceptions import AuthenticationError
from ...services.audit.service import audit_service
from ...database import get_database
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class AuthenticationMiddleware:
    """Enhanced authentication middleware with comprehensive security features."""

    def __init__(self):
        """Initialize authentication middleware with configuration."""
        self.security = security_manager
        self.bearer = HTTPBearer()

        # Redis connection for rate limiting and token blacklist
        try:
            self.redis = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                password=settings.REDIS_PASSWORD,
                decode_responses=True
            )
            logger.info("Redis connection established")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {str(e)}")
            self.redis = None

        # Rate limiting configuration
        self.rate_limit_config = {
            'window_seconds': 900,  # 15 minutes
            'max_requests': {
                'default': 100,
                'auth_endpoints': 20,
                'sensitive_endpoints': 50
            }
        }

        # Path configurations
        self.public_paths = {
            '/api/v1/auth/login',
            '/api/v1/auth/register',
            '/api/v1/auth/verify-email',
            '/docs',
            '/redoc',
            '/openapi.json'
        }

        self.sensitive_paths = {
            '/api/v1/admin',
            '/api/v1/centers/approve',
            '/api/v1/users/update-role'
        }

        # Security settings
        self.max_token_age = timedelta(hours=12)
        self.suspicious_ip_threshold = 100

        logger.info("Authentication middleware initialized with enhanced security")

    async def __call__(self, request: Request, call_next: Callable) -> Any:
        """Process each request for authentication and security checks."""
        try:
            path = request.url.path
            start_time = datetime.utcnow()

            # Skip authentication for public endpoints
            if self._is_public_endpoint(path):
                return await call_next(request)

            # Perform security checks
            await self._security_checks(request)

            # Rate limiting check
            await self._check_rate_limit(request)

            # Extract and validate token
            token = await self._extract_token(request)
            if not token:
                raise AuthenticationError("No valid authorization token provided")

            # Validate token and get user data
            token_data = await self._validate_token(token)
            user_data = await self._get_user_data(token_data)

            # Check token freshness for sensitive operations
            if self._is_sensitive_operation(path):
                if not self._is_token_fresh(token_data):
                    raise AuthenticationError("This operation requires a fresh login")

            # Add user data to request state
            request.state.user = user_data
            request.state.auth_time = start_time

            # Process request
            response = await call_next(request)

            # Audit logging for sensitive operations
            if self._is_sensitive_operation(path):
                await self._log_sensitive_operation(request, user_data, start_time)

            return response

        except AuthenticationError as auth_error:
            logger.warning(f"Authentication failed: {str(auth_error)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(auth_error),
                headers={"WWW-Authenticate": "Bearer"}
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Middleware error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error"
            )

    async def _security_checks(self, request: Request) -> None:
        """Perform security checks on request."""
        try:
            # Validate client IP
            client_ip = request.client.host
            if not self.security.validate_ip_address(client_ip):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid IP address"
                )

            # Check for suspicious activity
            if await self._is_suspicious_ip(client_ip):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Suspicious activity detected"
                )

            # Validate request headers
            if not self._validate_headers(request.headers):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid request headers"
                )

            # Validate request origin for CORS
            origin = request.headers.get("origin")
            if origin and not self._validate_origin(origin):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Invalid request origin"
                )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Security check error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Security check failed"
            )

    async def _check_rate_limit(self, request: Request) -> None:
        """Check if request is within rate limits."""
        try:
            if not self.redis:
                logger.warning("Rate limiting skipped due to Redis unavailability")
                return

            client_ip = request.client.host
            path = request.url.path

            # Determine rate limit based on endpoint
            if path.startswith('/api/v1/auth/'):
                max_requests = self.rate_limit_config['max_requests']['auth_endpoints']
            elif self._is_sensitive_operation(path):
                max_requests = self.rate_limit_config['max_requests']['sensitive_endpoints']
            else:
                max_requests = self.rate_limit_config['max_requests']['default']

            # Check rate limit
            key = f"rate_limit:{client_ip}:{path}"
            current = self.redis.get(key)

            if current and int(current) >= max_requests:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded"
                )

            # Update request count
            pipe = self.redis.pipeline()
            pipe.incr(key)
            pipe.expire(key, self.rate_limit_config['window_seconds'])
            pipe.execute()

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Rate limit check error: {str(e)}")
            # Allow request if rate limit check fails
            return None

    async def _validate_token(self, token: str) -> Dict[str, Any]:
        """Validate and decode authentication token."""
        try:
            # Check token blacklist
            if await self._is_token_blacklisted(token):
                raise AuthenticationError("Token has been revoked")

            # Decode and verify token
            payload = jwt.decode(
                token,
                settings.jwt_secret_key,
                algorithms=[settings.jwt_algorithm]
            )

            # Verify token type
            if payload.get("type") != "access":
                raise AuthenticationError("Invalid token type")

            # Verify token age
            if not self._verify_token_age(payload):
                raise AuthenticationError("Token has expired")

            logger.info(f"Token validated successfully for user ID: {payload['sub']}")
            return payload

        except jwt.ExpiredSignatureError:
            raise AuthenticationError("Token has expired")
        except jwt.InvalidTokenError as e:
            raise AuthenticationError(f"Invalid token: {str(e)}")
        except Exception as e:
            logger.error(f"Token validation error: {str(e)}")
            raise AuthenticationError("Token validation failed")

    def _is_public_endpoint(self, path: str) -> bool:
        """Check if endpoint is public."""
        return path in self.public_paths

    def _is_sensitive_operation(self, path: str) -> bool:
        """Check if operation requires additional security."""
        return path in self.sensitive_paths

    def _validate_headers(self, headers: Dict[str, str]) -> bool:
        """Validate request headers for security."""
        required_headers = {'user-agent', 'accept'}
        return all(header in headers for header in required_headers)

    def _validate_origin(self, origin: str) -> bool:
        """Validate request origin against allowed origins."""
        try:
            parsed = urlparse(origin)
            return parsed.netloc in settings.allowed_origins
        except Exception:
            return False

    async def _is_suspicious_ip(self, ip: str) -> bool:
        """Check if IP shows suspicious activity."""
        try:
            if not self.redis:
                return False
            key = f"ip_requests:{ip}"
            count = self.redis.get(key)
            return count and int(count) > self.suspicious_ip_threshold
        except Exception as e:
            logger.error(f"Suspicious IP check error: {str(e)}")
            return False

    async def _is_token_blacklisted(self, token: str) -> bool:
        """Check if a token is blacklisted."""
        try:
            if not self.redis:
                return False
            return self.redis.exists(f"blacklisted_token:{token}")
        except Exception as e:
            logger.error(f"Token blacklist check error: {str(e)}")
            return False

    def _verify_token_age(self, payload: Dict[str, Any]) -> bool:
        """Verify the age of the token."""
        issued_at = datetime.utcfromtimestamp(payload.get("iat", 0))
        return (datetime.utcnow() - issued_at) < self.max_token_age

    def _is_token_fresh(self, token_data: Dict[str, Any]) -> bool:
        """Check if the token is fresh."""
        issued_at = datetime.utcfromtimestamp(token_data.get("iat", 0))
        return (datetime.utcnow() - issued_at) < timedelta(minutes=5)

    async def _log_sensitive_operation(self, request: Request, user_data: Dict[str, Any], start_time: datetime) -> None:
        """Log sensitive operations for auditing."""
        try:
            duration = (datetime.utcnow() - start_time).total_seconds()
            await audit_service.log_sensitive_operation(
                user_id=user_data["id"],
                path=request.url.path,
                method=request.method,
                duration=duration,
                ip_address=request.client.host
            )
            logger.info(f"Sensitive operation logged for user ID: {user_data['id']}")
        except Exception as e:
            logger.error(f"Failed to log sensitive operation: {str(e)}")


# Initialize middleware
auth_middleware = AuthenticationMiddleware()