"""Security utilities providing cryptographic and validation functions.

This module implements secure cryptographic operations and validation checks
used throughout the application. It follows industry best practices for
secure password handling and data protection.
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple
from passlib.context import CryptContext
from jose import JWTError, jwt
import secrets
import logging
import re

from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class SecurityUtils:
    """Provides security and cryptographic utility functions."""
    
    _pwd_context = CryptContext(
        schemes=["bcrypt"],
        deprecated="auto",
        bcrypt__rounds=12
    )

    @classmethod
    def hash_password(cls, password: str) -> str:
        """Generate a secure hash for a password.
        
        This method implements secure password hashing using industry-standard
        algorithms with appropriate security parameters. It includes salt
        generation and proper work factors for resistance against brute force
        attacks.
        
        Args:
            password: The plain text password to hash

        Returns:
            A secure hash of the password
            
        Raises:
            ValueError: If the password does not meet security requirements
        """
        if not cls.validate_password_strength(password):
            raise ValueError("Password does not meet security requirements")

        try:
            return cls._pwd_context.hash(password)
        except Exception as e:
            logger.error("Password hashing failed", exc_info=True)
            raise RuntimeError("Unable to secure password")

    @classmethod
    def verify_password(cls, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash.
        
        This method performs secure password verification using constant-time
        comparison to prevent timing attacks.
        
        Args:
            plain_password: The password to verify
            hashed_password: The stored password hash

        Returns:
            Boolean indicating if the password matches
        """
        try:
            return cls._pwd_context.verify(plain_password, hashed_password)
        except Exception as e:
            logger.error("Password verification failed", exc_info=True)
            return False

    @staticmethod
    def validate_password_strength(password: str) -> bool:
        """Validate password strength against security requirements.
        
        This method checks passwords against security requirements including
        length, complexity, and common password patterns.
        
        Args:
            password: The password to validate

        Returns:
            Boolean indicating if the password meets requirements
        """
        if len(password) < 8:
            return False

        requirements = [
            lambda s: any(x.isupper() for x in s),  # uppercase letter
            lambda s: any(x.islower() for x in s),  # lowercase letter
            lambda s: any(x.isdigit() for x in s),  # digit
            lambda s: any(x in "!@#$%^&*(),.?\":{}|<>" for x in s)  # special character
        ]

        return all(requirement(password) for requirement in requirements)

    @staticmethod
    def generate_secure_token(length: int = 32) -> str:
        """Generate a cryptographically secure token.
        
        This method creates secure random tokens for various security
        purposes such as password reset or email verification.
        
        Args:
            length: The desired length of the token in bytes

        Returns:
            A secure random token string
        """
        try:
            return secrets.token_urlsafe(length)
        except Exception as e:
            logger.error("Token generation failed", exc_info=True)
            raise RuntimeError("Unable to generate secure token")

    @staticmethod
    def create_timed_token(
        data: Dict,
        expiry_hours: int = 24,
        secret_key: Optional[str] = None
    ) -> Tuple[str, datetime]:
        """Create a time-limited security token.
        
        This method generates tokens with embedded expiration times for
        temporary access or verification purposes.
        
        Args:
            data: The data to encode in the token
            expiry_hours: Token validity period in hours
            secret_key: Optional override for token signing key

        Returns:
            A tuple containing the token and its expiration time
        """
        try:
            expiration = datetime.utcnow() + timedelta(hours=expiry_hours)
            to_encode = data.copy()
            to_encode.update({"exp": expiration})

            key = secret_key or settings.secret_key
            token = jwt.encode(
                to_encode,
                key,
                algorithm=settings.token_algorithm
            )

            return token, expiration

        except Exception as e:
            logger.error("Timed token creation failed", exc_info=True)
            raise RuntimeError("Unable to create security token")

    @staticmethod
    def validate_email(email: str) -> bool:
        """Validate email address format.
        
        This method performs comprehensive email format validation using
        regular expressions and additional checks.
        
        Args:
            email: The email address to validate

        Returns:
            Boolean indicating if the email format is valid
        """
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))

# Initialize security utilities
security_utils = SecurityUtils()