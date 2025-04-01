import bcrypt
import secrets
import logging
from typing import Optional, Tuple
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

def generate_salt(rounds: int = 12) -> Optional[bytes]:
    """
    Generate a salt for password hashing.
    
    Args:
        rounds (int): The number of rounds for salt generation. Default is 12.
    
    Returns:
        Optional[bytes]: The generated salt, or None if an error occurs.
    """
    if rounds <= 0:
        logger.error("Invalid rounds value for salt generation: %d", rounds)
        return None
    try:
        return bcrypt.gensalt(rounds=rounds)
    except Exception as e:
        logger.error(f"Error generating salt: {str(e)}")
        return None

def hash_password(password: str, salt: Optional[bytes] = None) -> Optional[str]:
    """
    Hash a password using bcrypt.
    
    Args:
        password (str): The plain text password to hash.
        salt (Optional[bytes]): The salt to use for hashing. If None, a new salt is generated.
    
    Returns:
        Optional[str]: The hashed password, or None if an error occurs.
    """
    if not password:
        logger.error("Password cannot be empty")
        return None
    try:
        if not salt:
            salt = generate_salt()
        if not salt:
            return None
        return bcrypt.hashpw(password.encode(), salt).decode()
    except Exception as e:
        logger.error(f"Error hashing password: {str(e)}")
        return None

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against a hash.
    
    Args:
        plain_password (str): The plain text password to verify.
        hashed_password (str): The hashed password to compare against.
    
    Returns:
        bool: True if the password matches the hash, False otherwise.
    """
    try:
        return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())
    except Exception as e:
        logger.error(f"Password verification error: {str(e)}")
        return False

def generate_token(length: int = 32) -> str:
    """
    Generate a secure random token.
    
    Args:
        length (int): The length of the token. Default is 32.
    
    Returns:
        str: The generated token.
    """
    try:
        token = secrets.token_urlsafe(length)
        logger.info("Token generated successfully")
        return token
    except Exception as e:
        logger.error(f"Error generating token: {str(e)}")
        return ""

def get_token_expiry(duration: timedelta) -> datetime:
    """
    Calculate token expiry timestamp.
    
    Args:
        duration (timedelta): The duration for which the token is valid.
    
    Returns:
        datetime: The expiry timestamp.
    """
    return datetime.utcnow() + duration

def is_token_expired(expiry_time: datetime) -> bool:
    """
    Check if a token has expired.
    
    Args:
        expiry_time (datetime): The expiry timestamp of the token.
    
    Returns:
        bool: True if the token has expired, False otherwise.
    """
    return datetime.utcnow() > expiry_time

def validate_password_strength(password: str) -> Tuple[bool, str]:
    """
    Validate password meets security requirements.
    
    Args:
        password (str): The password to validate.
    
    Returns:
        Tuple[bool, str]: A tuple containing a boolean indicating validity and a message.
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long."
    if not any(c.isupper() for c in password):
        return False, "Password must contain at least one uppercase letter."
    if not any(c.islower() for c in password):
        return False, "Password must contain at least one lowercase letter."
    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one digit."
    if not any(c in '!@#$%^&*(),.?":{}|<>' for c in password):
        return False, "Password must contain at least one special character."
    return True, "Password is strong."