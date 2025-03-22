# backend/app/core/utils/security_utils.py

import bcrypt
import secrets
import logging
from typing import Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

def generate_salt(rounds: int = 12) -> bytes:
    """Generate a salt for password hashing."""
    return bcrypt.gensalt(rounds=rounds)

def hash_password(password: str, salt: Optional[bytes] = None) -> str:
    """Hash password using bcrypt."""
    if not salt:
        salt = generate_salt()
    return bcrypt.hashpw(password.encode(), salt).decode()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash."""
    try:
        return bcrypt.checkpw(
            plain_password.encode(),
            hashed_password.encode()
        )
    except Exception as e:
        logger.error(f"Password verification error: {str(e)}")
        return False

def generate_token(length: int = 32) -> str:
    """Generate a secure random token."""
    return secrets.token_urlsafe(length)

def get_token_expiry(duration: timedelta) -> datetime:
    """Calculate token expiry timestamp."""
    return datetime.utcnow() + duration

def validate_password_strength(password: str) -> bool:
    """Validate password meets security requirements."""
    if len(password) < 8:
        return False
    if not any(c.isupper() for c in password):
        return False
    if not any(c.islower() for c in password):
        return False
    if not any(c.isdigit() for c in password):
        return False
    if not any(c in '!@#$%^&*(),.?":{}|<>' for c in password):
        return False
    return True