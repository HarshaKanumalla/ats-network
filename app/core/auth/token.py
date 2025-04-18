# backend/app/core/auth/token.py

from datetime import datetime, timedelta
from typing import Dict, Any, Tuple, Optional
import jwt
import secrets
import logging
from bson import ObjectId

from ...database import get_database
from ..exceptions import TokenError, SecurityError
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class TokenService:
    """Manages token generation, validation, and lifecycle."""

    def __init__(self):
        """Initialize token service with configuration."""
        self.db = None
        self.security_service = None
        self._initialized = False

        # Token settings
        self.access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        self.refresh_token_expires = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        self.token_algorithm = settings.TOKEN_ALGORITHM

        # Token rotation settings
        self.refresh_token_rotation = True
        self.refresh_token_reuse_interval = timedelta(minutes=5)

        # Token tracking settings
        self.track_token_usage = True
        self.max_token_usage = 1000  # Maximum uses per token

        logger.info("Token service initialized with enhanced security features")

    async def initialize(self):
        """Initialize token service with required dependencies."""
        if not self._initialized:
            from ..security import security_manager
            self.security_service = security_manager
            self._initialized = True
            logger.info("Token service dependencies initialized")

    async def create_tokens(
        self,
        user_id: str,
        user_data: Dict[str, Any]
    ) -> Tuple[str, str]:
        """
        Create access and refresh token pair with security measures.

        Args:
            user_id: User identifier
            user_data: Additional user information for token payload

        Returns:
            Tuple containing access token and refresh token

        Raises:
            TokenError: If token creation fails
        """
        try:
            if not ObjectId.is_valid(user_id):
                raise ValueError("Invalid user ID format")

            # Generate token identifiers
            access_jti = secrets.token_urlsafe(32)
            refresh_jti = secrets.token_urlsafe(32)

            # Create access token
            access_token_data = {
                "sub": user_id,
                "type": "access",
                "jti": access_jti,
                "role": user_data.get("role"),
                "permissions": user_data.get("permissions", []),
                "center_id": user_data.get("center_id"),
                "iat": datetime.utcnow(),
                "exp": datetime.utcnow() + self.access_token_expires
            }

            access_token = jwt.encode(
                access_token_data,
                settings.ACCESS_TOKEN_SECRET,
                algorithm=self.token_algorithm
            )

            # Create refresh token
            refresh_token_data = {
                "sub": user_id,
                "type": "refresh",
                "jti": refresh_jti,
                "iat": datetime.utcnow(),
                "exp": datetime.utcnow() + self.refresh_token_expires
            }

            refresh_token = jwt.encode(
                refresh_token_data,
                settings.REFRESH_TOKEN_SECRET,
                algorithm=self.token_algorithm
            )

            # Store token metadata
            await self._store_token_metadata(
                access_jti=access_jti,
                refresh_jti=refresh_jti,
                user_id=user_id
            )

            logger.info(f"Tokens created successfully for user ID: {user_id}")
            return access_token, refresh_token

        except Exception as e:
            logger.error(f"Token creation error for user ID {user_id}: {str(e)}")
            raise TokenError("Failed to create authentication tokens")

    async def validate_token(
        self,
        token: str,
        token_type: str = "access"
    ) -> Dict[str, Any]:
        """
        Validate token and return decoded payload.

        Args:
            token: Token to validate
            token_type: Type of token (access/refresh)

        Returns:
            Decoded token payload

        Raises:
            TokenError: If token is invalid
        """
        try:
            # Select secret based on token type
            secret = (settings.ACCESS_TOKEN_SECRET if token_type == "access"
                      else settings.REFRESH_TOKEN_SECRET)

            # Decode and verify token
            payload = jwt.decode(
                token,
                secret,
                algorithms=[self.token_algorithm]
            )

            # Verify token type
            if payload.get("type") != token_type:
                raise TokenError("Invalid token type")

            # Verify token is not revoked
            if await self._is_token_revoked(payload["jti"]):
                raise TokenError("Token has been revoked")

            # Track token usage
            if self.track_token_usage:
                await self._track_token_usage(payload["jti"])

            logger.info(f"Token validated successfully for user ID: {payload['sub']}")
            return payload

        except jwt.ExpiredSignatureError:
            raise TokenError("Token has expired")
        except jwt.InvalidTokenError as e:
            raise TokenError(f"Invalid token: {str(e)}")
        except Exception as e:
            logger.error(f"Token validation error: {str(e)}")
            raise TokenError("Token validation failed")

    async def refresh_tokens(
        self,
        refresh_token: str,
        user_data: Optional[Dict[str, Any]] = None
    ) -> Tuple[str, str]:
        """
        Refresh access token using refresh token with security checks.

        Args:
            refresh_token: Current refresh token
            user_data: Optional updated user data

        Returns:
            New access and refresh tokens

        Raises:
            TokenError: If refresh operation fails
        """
        try:
            # Validate refresh token
            payload = await self.validate_token(refresh_token, "refresh")

            # Check token reuse if rotation is enabled
            if self.refresh_token_rotation:
                if await self._is_token_reused(payload["jti"]):
                    await self._handle_token_reuse(payload["sub"])
                    raise TokenError("Refresh token reuse detected")

            # Create new tokens
            new_access_token, new_refresh_token = await self.create_tokens(
                user_id=payload["sub"],
                user_data=user_data or {}
            )

            # Revoke old refresh token if rotation is enabled
            if self.refresh_token_rotation:
                await self.revoke_token(payload["jti"])

            logger.info(f"Tokens refreshed successfully for user ID: {payload['sub']}")
            return new_access_token, new_refresh_token

        except TokenError:
            raise
        except Exception as e:
            logger.error(f"Token refresh error: {str(e)}")
            raise TokenError("Failed to refresh tokens")

    async def revoke_token(self, token_id: str) -> None:
        """
        Revoke a specific token and add it to the blacklist.

        Args:
            token_id: The unique identifier of the token to revoke

        Raises:
            TokenError: If the token revocation fails
        """
        try:
            db = await get_database()

            # Add to blacklist in Redis
            if self.redis:
                await self.redis.setex(
                    f"blacklist:token:{token_id}",
                    int(self.refresh_token_expires.total_seconds()),
                    "revoked"
                )
            else:
                logger.warning("Redis unavailable, skipping token blacklist update")

            # Update token status in database
            await db.token_metadata.update_one(
                {"jti": token_id},
                {
                    "$set": {
                        "status": "revoked",
                        "revoked_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    }
                }
            )

            logger.info(f"Token revoked successfully: {token_id}")

        except Exception as e:
            logger.error(f"Token revocation error for token ID {token_id}: {str(e)}")
            raise TokenError(f"Failed to revoke token: {str(e)}")

    async def revoke_all_user_tokens(self, user_id: str) -> None:
        """
        Revoke all tokens for a specific user.

        Args:
            user_id: User identifier

        Raises:
            TokenError: If revocation fails
        """
        try:
            db = await get_database()

            # Get active tokens for user
            active_tokens = await db.token_metadata.find({
                "userId": ObjectId(user_id),
                "revokedAt": None
            }).to_list(None)

            # Revoke all tokens
            for token in active_tokens:
                await self.revoke_token(token["jti"])

            logger.info(f"All tokens revoked for user ID: {user_id}")

        except Exception as e:
            logger.error(f"User token revocation error: {str(e)}")
            raise TokenError("Failed to revoke user tokens")

    async def _store_token_metadata(
        self,
        access_jti: str,
        refresh_jti: str,
        user_id: str
    ) -> None:
        """
        Store token metadata for tracking.

        Args:
            access_jti: Access token identifier
            refresh_jti: Refresh token identifier
            user_id: User identifier

        Raises:
            TokenError: If metadata storage fails
        """
        try:
            db = await get_database()

            # Store access token metadata
            await db.token_metadata.insert_one({
                "jti": access_jti,
                "userId": ObjectId(user_id),
                "type": "access",
                "usageCount": 0,
                "createdAt": datetime.utcnow(),
                "expiresAt": datetime.utcnow() + self.access_token_expires
            })

            # Store refresh token metadata
            await db.token_metadata.insert_one({
                "jti": refresh_jti,
                "userId": ObjectId(user_id),
                "type": "refresh",
                "usageCount": 0,
                "createdAt": datetime.utcnow(),
                "expiresAt": datetime.utcnow() + self.refresh_token_expires
            })

            logger.info(f"Token metadata stored for user ID: {user_id}")

        except Exception as e:
            logger.error(f"Token metadata storage error: {str(e)}")
            raise TokenError("Failed to store token metadata")

    async def cleanup_blacklist(self) -> None:
        """
        Clean up expired entries from token blacklist.

        Raises:
            TokenError: If cleanup fails
        """
        try:
            if not self.redis:
                logger.warning("Redis unavailable, skipping blacklist cleanup")
                return

            pattern = "blacklist:token:*"
            cursor = 0

            while True:
                cursor, keys = await self.redis.scan(
                    cursor=cursor,
                    match=pattern
                )

                if keys:
                    # Check and remove expired keys
                    pipeline = self.redis.pipeline()
                    for key in keys:
                        ttl = await self.redis.ttl(key)
                        if ttl <= 0:
                            pipeline.delete(key)

                    await pipeline.execute()

                if cursor == 0:
                    break

            logger.info("Completed blacklist cleanup")

        except Exception as e:
            logger.error(f"Blacklist cleanup error: {str(e)}")
            raise TokenError("Failed to clean up token blacklist")


# Initialize token service
token_service = TokenService()