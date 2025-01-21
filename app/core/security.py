# backend/app/core/security.py

from passlib.context import CryptContext
from typing import Optional
import secrets
from datetime import datetime, timedelta

# Password hashing configuration
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password: str) -> str:
    """Generate a secure hash from a password."""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)

def create_verification_token() -> str:
    """Generate a secure token for email verification."""
    return secrets.token_urlsafe(32)

def create_reset_token() -> tuple[str, datetime]:
    """Create a password reset token with expiration."""
    expiration = datetime.utcnow() + timedelta(hours=24)
    token = secrets.token_urlsafe(32)
    return token, expiration