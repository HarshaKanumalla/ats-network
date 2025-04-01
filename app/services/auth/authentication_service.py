from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple, Callable
import logging
import jwt
import bcrypt
import redis
import secrets
from fastapi import HTTPException, status, Request
from bson import ObjectId

from ...core.security import SecurityManager
from ...core.auth.token import TokenService
from ...core.exceptions import RateLimitError
from ...services.email.email_service import EmailService
from ...services.s3.s3_service import S3Service
from ...database import get_database, database_transaction
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class RateLimiter:
    """Handle rate limiting for authentication attempts."""
    
    def __init__(self):
        self.redis = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.redis_password,
            decode_responses=True
        )
    
    async def check_rate_limit(self, key: str, action: str) -> bool:
        """Check if rate limit is exceeded."""
        attempts_key = f"ratelimit:{action}:{key}"
        lockout_key = f"lockout:{action}:{key}"
        
        if await self.redis.get(lockout_key):
            return False
        
        attempts = int(await self.redis.get(attempts_key) or 0)
        return attempts < settings.MAX_ATTEMPTS[action]
    
    async def increment_attempts(self, key: str, action: str) -> None:
        """Increment attempt counter and handle lockout."""
        attempts_key = f"ratelimit:{action}:{key}"
        lockout_key = f"lockout:{action}:{key}"
        
        pipe = self.redis.pipeline()
        pipe.incr(attempts_key)
        pipe.expire(attempts_key, settings.RATE_LIMIT_WINDOW)
        attempts = (await pipe.execute())[0]
        
        if attempts >= settings.MAX_ATTEMPTS[action]:
            await self.redis.setex(
                lockout_key,
                settings.LOCKOUT_DURATION,
                1
            )

class AuthenticationService:
    """Service for managing authentication and session handling."""
    
    def __init__(self):
        """Initialize authentication service with required components."""
        self.security = SecurityManager()
        self.token_service = TokenService()
        self.email_service = EmailService()
        self.s3_service = S3Service()
        
        # Redis for rate limiting and token blacklisting
        self.redis = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.redis_password,
            decode_responses=True
        )
        
        # Settings
        self.max_login_attempts = 5
        self.lockout_duration = 1800  # 30 minutes
        self.rate_limit_window = 3600  # 1 hour
        self.access_token_expires = timedelta(minutes=30)
        self.refresh_token_expires = timedelta(days=7)
        
        logger.info("Authentication service initialized with enhanced security")

    async def login(self, email: str, password: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Authenticate user and create session."""
        try:
            db = await get_database()
            
            if not await rate_limiter.check_rate_limit(email, 'login'):
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many login attempts"
                )
            
            user = await db.users.find_one({"email": email})
            if not user:
                await rate_limiter.increment_attempts(email, 'login')
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid credentials"
                )
            
            if not self.security.verify_password(password, user["password"]):
                await rate_limiter.increment_attempts(email, 'login')
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid credentials"
                )
            
            session = await self.create_session(str(user["_id"]), metadata)
            
            access_token = self.token_service.create_access_token(
                data={"sub": str(user["_id"])},
                expires_delta=self.access_token_expires
            )
            refresh_token = self.token_service.create_refresh_token(
                data={"sub": str(user["_id"])},
                expires_delta=self.refresh_token_expires
            )
            
            return {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "session_id": session["sessionId"],
                "token_type": "bearer"
            }
            
        except Exception as e:
            logger.error(f"Login error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Login failed"
            )

    async def logout(self, access_token: str, refresh_token: str, session_id: str) -> Dict[str, Any]:
        """Handle user logout and cleanup."""
        try:
            db = await get_database()
            
            await db.sessions.update_one(
                {"sessionId": session_id},
                {
                    "$set": {
                        "isActive": False,
                        "endedAt": datetime.utcnow()
                    }
                }
            )
            
            await self._blacklist_token(access_token, "access")
            await self._blacklist_token(refresh_token, "refresh")
            
            return {"status": "success", "message": "Logged out successfully"}
            
        except Exception as e:
            logger.error(f"Logout error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Logout failed"
            )

    async def request_password_reset(self, email: str) -> Dict[str, Any]:
        """Request password reset with rate limiting and token generation."""
        try:
            if not await rate_limiter.check_rate_limit(email, 'password_reset'):
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many reset attempts"
                )

            db = await get_database()
            user = await db.users.find_one({"email": email})
            
            if not user:
                return {"status": "success", "message": "Reset instructions sent"}
            
            reset_token = secrets.token_urlsafe(32)
            reset_expires = datetime.utcnow() + timedelta(hours=1)
            
            await db.users.update_one(
                {"_id": user["_id"]},
                {
                    "$set": {
                        "resetToken": reset_token,
                        "resetTokenExpires": reset_expires,
                        "updatedAt": datetime.utcnow()
                    }
                }
            )
            
            await self.email_service.send_password_reset(
                email=user["email"],
                name=f"{user['firstName']} {user['lastName']}",
                reset_token=reset_token
            )
            
            return {"status": "success", "message": "Reset instructions sent"}
            
        except Exception as e:
            logger.error(f"Password reset request error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to process reset request"
            )

    async def verify_reset_token(self, reset_token: str, new_password: str) -> Dict[str, Any]:
        """Verify and process password reset."""
        try:
            db = await get_database()
            
            user = await db.users.find_one({
                "resetToken": reset_token,
                "resetTokenExpires": {"$gt": datetime.utcnow()}
            })
            
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid or expired reset token"
                )
            
            hashed_password = self.security.hash_password(new_password)
            
            await db.users.update_one(
                {"_id": user["_id"]},
                {
                    "$set": {
                        "password": hashed_password,
                        "updatedAt": datetime.utcnow()
                    },
                    "$unset": {
                        "resetToken": "",
                        "resetTokenExpires": ""
                    }
                }
            )
            
            await db.sessions.update_many(
                {"userId": user["_id"]},
                {
                    "$set": {
                        "isActive": False,
                        "endedAt": datetime.utcnow()
                    }
                }
            )
            
            return {"status": "success", "message": "Password reset successful"}
            
        except Exception as e:
            logger.error(f"Password reset verification error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to reset password"
            )

    async def refresh_token(self, refresh_token: str) -> Dict[str, Any]:
        """Generate new access token using refresh token."""
        try:
            payload = await self.verify_token(refresh_token, "refresh")
            user_id = payload.get("sub")
            
            if not user_id:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid refresh token"
                )
                
            access_token = self.token_service.create_access_token(
                data={"sub": user_id},
                expires_delta=self.access_token_expires
            )
            
            return {
                "access_token": access_token,
                "token_type": "bearer"
            }
            
        except Exception as e:
            logger.error(f"Token refresh error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Failed to refresh token"
            )

    async def create_session(self, user_id: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Create and track user session."""
        try:
            db = await get_database()
            
            session = {
                "userId": ObjectId(user_id),
                "sessionId": secrets.token_urlsafe(32),
                "userAgent": metadata.get("userAgent"),
                "ipAddress": metadata.get("ipAddress"),
                "lastActivity": datetime.utcnow(),
                "isActive": True,
                "expiresAt": datetime.utcnow() + timedelta(days=1)
            }
            
            await db.sessions.insert_one(session)
            return {"sessionId": session["sessionId"]}
            
        except Exception as e:
            logger.error(f"Session creation error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create session"
            )

    async def validate_session(self, session_id: str, user_id: str) -> bool:
        """Validate session status."""
        try:
            db = await get_database()
            
            session = await db.sessions.find_one({
                "sessionId": session_id,
                "userId": ObjectId(user_id),
                "isActive": True,
                "expiresAt": {"$gt": datetime.utcnow()}
            })
            
            return bool(session)
            
        except Exception as e:
            logger.error(f"Session validation error: {str(e)}")
            return False

    async def extend_session(self, session_id: str) -> Dict[str, Any]:
        """Extend session expiration."""
        try:
            db = await get_database()
            
            result = await db.sessions.update_one(
                {"sessionId": session_id},
                {
                    "$set": {
                        "lastActivity": datetime.utcnow(),
                        "expiresAt": datetime.utcnow() + timedelta(days=1)
                    }
                }
            )
            
            if result.modified_count == 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid session"
                )
                
            return {"status": "success", "message": "Session extended"}
            
        except Exception as e:
            logger.error(f"Session extension error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to extend session"
            )

    async def verify_token(self, token: str, token_type: str = "access") -> Dict[str, Any]:
        """Verify token validity and blacklist status."""
        try:
            is_blacklisted = await self.redis.get(f"blacklist:{token_type}:{token}")
            if is_blacklisted:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token has been invalidated"
                )
            
            payload = jwt.decode(
                token,
                settings.SECRET_KEY,
                algorithms=[settings.ALGORITHM]
            )
            
            return payload
            
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired"
            )
        except jwt.JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )

    async def _blacklist_token(self, token: str, token_type: str = "refresh") -> None:
        """Add token to blacklist with TTL."""
        try:
            payload = jwt.decode(
                token,
                settings.SECRET_KEY,
                algorithms=[settings.ALGORITHM]
            )
            exp = datetime.fromtimestamp(payload["exp"])
            ttl = max(0, (exp - datetime.utcnow()).total_seconds())
            
            await self.redis.setex(
                f"blacklist:{token_type}:{token}",
                int(ttl),
                "1"
            )
            
        except Exception as e:
            logger.error(f"Token blacklisting error: {str(e)}")

    def get_security_headers(self) -> Dict[str, str]:
        """Get recommended security headers."""
        return {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": "default-src 'self'",
            "Referrer-Policy": "strict-origin-when-cross-origin"
        }

    async def initiate_account_recovery(self, email: str, recovery_type: str) -> Dict[str, Any]:
        """Initiate account recovery process."""
        try:
            db = await get_database()
            user = await db.users.find_one({"email": email})
            
            if not user:
                return {"status": "success"}
            
            if recovery_type == "email":
                recovery_token = secrets.token_urlsafe(32)
                expires = datetime.utcnow() + timedelta(hours=1)
                
                await db.users.update_one(
                    {"_id": user["_id"]},
                    {
                        "$set": {
                            "recoveryToken": recovery_token,
                            "recoveryExpires": expires,
                            "recoveryType": recovery_type
                        }
                    }
                )
                
                await self.email_service.send_recovery_instructions(
                    email=user["email"],
                    name=f"{user['firstName']} {user['lastName']}",
                    recovery_token=recovery_token
                )
            
            return {"status": "success", "message": "Recovery instructions sent"}
            
        except Exception as e:
            logger.error(f"Account recovery error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to initiate recovery"
            )

# Initialize services
auth_service = AuthenticationService()
rate_limiter = RateLimiter()