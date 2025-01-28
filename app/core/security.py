"""Core security functionality."""
from passlib.context import CryptContext
import secrets
from datetime import datetime, timedelta
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

class SecurityManager:
    """Handles security-related operations."""
    
    _pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    @classmethod
    def get_password_hash(cls, password: str) -> str:
        """Generate a secure hash from a password."""
        try:
            return cls._pwd_context.hash(password)
        except Exception as e:
            logger.error(f"Password hashing failed: {str(e)}")
            raise

    @classmethod
    def verify_password(cls, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash."""
        try:
            return cls._pwd_context.verify(plain_password, hashed_password)
        except Exception as e:
            logger.error(f"Password verification failed: {str(e)}")
            return False

    @staticmethod
    def create_verification_token() -> str:
        """Generate a secure token for email verification."""
        try:
            return secrets.token_urlsafe(32)
        except Exception as e:
            logger.error(f"Verification token creation failed: {str(e)}")
            raise

    @staticmethod
    def create_reset_token() -> Tuple[str, datetime]:
        """Create a password reset token with expiration."""
        try:
            expiration = datetime.utcnow() + timedelta(hours=24)
            token = secrets.token_urlsafe(32)
            return token, expiration
        except Exception as e:
            logger.error(f"Reset token creation failed: {str(e)}")
            raise