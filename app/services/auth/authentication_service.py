# backend/app/services/auth/authentication_service.py

from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
import logging
import jwt
import bcrypt
import redis
import secrets
from fastapi import HTTPException, status
from bson import ObjectId

from ...core.security import SecurityManager
from ...core.auth.token import TokenService
from ...services.email.email_service import EmailService
from ...services.s3.s3_service import S3Service
from ...database import get_database, database_transaction
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class AuthenticationService:
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
        
        # Rate limiting settings
        self.max_login_attempts = 5
        self.lockout_duration = 1800  # 30 minutes
        self.rate_limit_window = 3600  # 1 hour
        
        # Token settings
        self.access_token_expires = timedelta(minutes=30)
        self.refresh_token_expires = timedelta(days=7)
        
        logger.info("Authentication service initialized with enhanced security")

    async def register_user(
        self,
        user_data: Dict[str, Any],
        documents: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle user registration with enhanced security and validation."""
        async with database_transaction() as session:
            try:
                db = await get_database()
                
                # Check email uniqueness
                if await db.users.find_one({"email": user_data["email"]}):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Email already registered"
                    )
                
                # Process and store documents
                document_urls = await self._process_registration_documents(
                    user_data["email"],
                    documents
                )
                
                # Hash password securely
                password_hash = await self.security.hash_password(
                    user_data["password"]
                )
                
                # Create verification token
                verification_token = secrets.token_urlsafe(32)
                
                # Create user record
                user_record = {
                    "email": user_data["email"],
                    "passwordHash": password_hash,
                    "firstName": user_data["firstName"],
                    "lastName": user_data["lastName"],
                    "phoneNumber": user_data["phoneNumber"],
                    "role": "pending",
                    "status": "pending",
                    "atsCenter": {
                        "name": user_data["centerName"],
                        "address": user_data["address"],
                        "city": user_data["city"],
                        "district": user_data["district"],
                        "state": user_data["state"],
                        "pinCode": user_data["pinCode"],
                        "coordinates": None  # Will be updated after verification
                    },
                    "documents": document_urls,
                    "verificationToken": verification_token,
                    "verificationExpires": datetime.utcnow() + timedelta(days=7),
                    "isActive": True,
                    "isVerified": False,
                    "createdAt": datetime.utcnow(),
                    "updatedAt": datetime.utcnow()
                }
                
                # Insert with transaction
                result = await db.users.insert_one(user_record, session=session)
                user_record["_id"] = result.inserted_id
                
                # Send verification email
                await self.email_service.send_registration_pending(
                    email=user_data["email"],
                    name=f"{user_data['firstName']} {user_data['lastName']}",
                    center_name=user_data["centerName"]
                )
                
                logger.info(f"Registered new user: {user_data['email']}")
                return {"id": str(result.inserted_id), "status": "pending"}
                
            except Exception as e:
                logger.error(f"Registration error: {str(e)}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Registration failed"
                )

    async def authenticate_user(
        self,
        email: str,
        password: str,
        client_ip: str
    ) -> Dict[str, Any]:
        """Authenticate user with rate limiting and security measures."""
        try:
            # Check rate limiting
            if await self._is_rate_limited(client_ip):
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many login attempts"
                )
                
            db = await get_database()
            
            # Get user and verify credentials
            user = await db.users.find_one({"email": email})
            if not user or not self.security.verify_password(
                password,
                user["passwordHash"]
            ):
                await self._handle_failed_login(email, client_ip)
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid credentials"
                )
            
            # Check account status
            if not user["isActive"]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Account is inactive"
                )
            
            if user["status"] != "approved":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Account pending approval"
                )
            
            # Generate tokens
            access_token, refresh_token = await self.token_service.create_tokens(
                str(user["_id"]),
                {
                    "role": user["role"],
                    "permissions": user.get("permissions", []),
                    "center_id": str(user["atsCenter"]["_id"]) if "atsCenter" in user else None
                }
            )
            
            # Update last login and reset failed attempts
            await db.users.update_one(
                {"_id": user["_id"]},
                {
                    "$set": {
                        "lastLogin": datetime.utcnow(),
                        "loginAttempts": 0,
                        "updatedAt": datetime.utcnow()
                    }
                }
            )
            
            # Clear rate limiting
            await self._clear_rate_limit(client_ip)
            
            return {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "user": self._format_user_response(user)
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Authentication error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Authentication failed"
            )

    async def refresh_token(
        self,
        refresh_token: str
    ) -> Dict[str, str]:
        """Refresh access token using refresh token."""
        try:
            # Verify refresh token
            payload = await self.token_service.verify_token(
                refresh_token,
                token_type="refresh"
            )
            
            # Check if token is blacklisted
            if await self._is_token_blacklisted(refresh_token):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token has been revoked"
                )
            
            # Get user data
            db = await get_database()
            user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
            
            if not user or not user["isActive"]:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User inactive or not found"
                )
            
            # Generate new tokens
            new_access_token, new_refresh_token = await self.token_service.create_tokens(
                str(user["_id"]),
                {
                    "role": user["role"],
                    "permissions": user.get("permissions", []),
                    "center_id": str(user["atsCenter"]["_id"]) if "atsCenter" in user else None
                }
            )
            
            # Blacklist old refresh token
            await self._blacklist_token(refresh_token)
            
            return {
                "access_token": new_access_token,
                "refresh_token": new_refresh_token
            }
            
        except Exception as e:
            logger.error(f"Token refresh error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Failed to refresh token"
            )

    async def _process_registration_documents(
        self,
        email: str,
        documents: Dict[str, Any]
    ) -> Dict[str, str]:
        """Process and store registration documents securely."""
        try:
            document_urls = {}
            for doc_type, file in documents.items():
                url = await self.s3_service.upload_document(
                    file=file,
                    folder=f"users/{email}/registration",
                    metadata={
                        "user_email": email,
                        "document_type": doc_type
                    }
                )
                document_urls[doc_type] = url
            return document_urls
            
        except Exception as e:
            logger.error(f"Document processing error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to process documents"
            )

    async def _handle_failed_login(
        self,
        email: str,
        client_ip: str
    ) -> None:
        """Handle failed login attempt with rate limiting."""
        try:
            # Increment failed attempts counter
            key = f"login_attempts:{client_ip}"
            attempts = await self.redis.incr(key)
            
            # Set expiry if first attempt
            if attempts == 1:
                await self.redis.expire(key, self.rate_limit_window)
            
            # Lock account if too many attempts
            if attempts >= self.max_login_attempts:
                await self._lock_account(email)
                
        except Exception as e:
            logger.error(f"Failed login handling error: {str(e)}")

    def _format_user_response(
        self,
        user: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Format user data for response."""
        return {
            "id": str(user["_id"]),
            "email": user["email"],
            "firstName": user["firstName"],
            "lastName": user["lastName"],
            "role": user["role"],
            "permissions": user.get("permissions", []),
            "atsCenter": user.get("atsCenter"),
            "lastLogin": user.get("lastLogin")
        }

class RateLimiter:
    """Service for implementing rate limiting."""
    
    def __init__(self):
        """Initialize rate limiter with Redis backend."""
        self.redis = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD,
            decode_responses=True,
            db=settings.REDIS_DB
        )
        
        # Rate limit configurations
        self.rate_limits = {
            'login': {
                'attempts': 5,
                'window': 300  # 5 minutes
            },
            'registration': {
                'attempts': 3,
                'window': 3600  # 1 hour
            },
            'password_reset': {
                'attempts': 3,
                'window': 3600  # 1 hour
            },
            'api': {
                'attempts': 100,
                'window': 60  # 1 minute
            }
        }

    async def check_rate_limit(
        self,
        key: str,
        rate_type: str = 'api',
        identifier: Optional[str] = None
    ) -> bool:
        """Check if request is within rate limits.
        
        Args:
            key: Base key for rate limiting
            rate_type: Type of rate limit to apply
            identifier: Optional identifier (e.g., IP address or user ID)
            
        Returns:
            bool: True if within limits, False if limit exceeded
        """
        try:
            rate_config = self.rate_limits[rate_type]
            
            # Build redis key
            redis_key = f"ratelimit:{rate_type}:{key}"
            if identifier:
                redis_key = f"{redis_key}:{identifier}"
            
            # Get current count
            current = await self.redis.get(redis_key)
            count = int(current) if current else 0
            
            if count >= rate_config['attempts']:
                return False
                
            # Update count in transaction
            pipe = self.redis.pipeline()
            if count == 0:
                pipe.setex(
                    redis_key,
                    rate_config['window'],
                    1
                )
            else:
                pipe.incr(redis_key)
            await pipe.execute()
            
            return True
            
        except Exception as e:
            logger.error(f"Rate limit check error: {str(e)}")
            return True  # Allow request if rate limiting fails

    async def reset_counter(
        self,
        key: str,
        rate_type: str = 'api',
        identifier: Optional[str] = None
    ) -> None:
        """Reset rate limit counter.
        
        Args:
            key: Base key for rate limiting
            rate_type: Type of rate limit
            identifier: Optional identifier
        """
        try:
            redis_key = f"ratelimit:{rate_type}:{key}"
            if identifier:
                redis_key = f"{redis_key}:{identifier}"
            
            await self.redis.delete(redis_key)
            
        except Exception as e:
            logger.error(f"Counter reset error: {str(e)}")

    async def get_remaining_attempts(
        self,
        key: str,
        rate_type: str = 'api',
        identifier: Optional[str] = None
    ) -> int:
        """Get remaining allowed attempts.
        
        Args:
            key: Base key for rate limiting
            rate_type: Type of rate limit
            identifier: Optional identifier
            
        Returns:
            int: Number of remaining attempts
        """
        try:
            rate_config = self.rate_limits[rate_type]
            
            redis_key = f"ratelimit:{rate_type}:{key}"
            if identifier:
                redis_key = f"{redis_key}:{identifier}"
            
            current = await self.redis.get(redis_key)
            count = int(current) if current else 0
            
            return max(0, rate_config['attempts'] - count)
            
        except Exception as e:
            logger.error(f"Remaining attempts check error: {str(e)}")
            return 0

    async def get_reset_time(
        self,
        key: str,
        rate_type: str = 'api',
        identifier: Optional[str] = None
    ) -> Optional[int]:
        """Get time until rate limit reset.
        
        Args:
            key: Base key for rate limiting
            rate_type: Type of rate limit
            identifier: Optional identifier
            
        Returns:
            Optional[int]: Seconds until reset, None if no active limit
        """
        try:
            redis_key = f"ratelimit:{rate_type}:{key}"
            if identifier:
                redis_key = f"{redis_key}:{identifier}"
            
            ttl = await self.redis.ttl(redis_key)
            return max(0, ttl) if ttl > -1 else None
            
        except Exception as e:
            logger.error(f"Reset time check error: {str(e)}")
            return None

# Initialize rate limiter
rate_limiter = RateLimiter()

# Add decorator for rate limiting endpoints
def rate_limit(
    rate_type: str = 'api',
    key_func: Optional[Callable] = None
):
    """Decorator for rate limiting endpoints.
    
    Args:
        rate_type: Type of rate limit to apply
        key_func: Optional function to generate rate limit key
    """
    async def decorator(request: Request):
        try:
            # Get rate limit key
            if key_func:
                key = key_func(request)
            else:
                key = request.url.path
            
            # Get client identifier (IP address)
            client_ip = request.client.host
            
            # Check rate limit
            if not await rate_limiter.check_rate_limit(
                key,
                rate_type,
                client_ip
            ):
                # Get reset time
                reset_time = await rate_limiter.get_reset_time(
                    key,
                    rate_type,
                    client_ip
                )
                
                raise RateLimitError(
                    message="Rate limit exceeded",
                    reset_time=datetime.utcnow() + timedelta(seconds=reset_time)
                    if reset_time else None
                )
                
        except RateLimitError:
            raise
        except Exception as e:
            logger.error(f"Rate limiting error: {str(e)}")
    
    return decorator

# Initialize authentication service
auth_service = AuthenticationService()