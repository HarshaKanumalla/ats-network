# backend/app/services/auth.py
from datetime import datetime, timedelta
from typing import Optional, Union
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
import logging
from bson import ObjectId

from ..config import get_settings
from ..models.user import User, UserInDB, TokenData, Role
from ..services.database import get_user_by_email, get_user_by_id

# System Info
SYSTEM_INFO = {
    "last_updated": "2024-12-19 18:20:27",
    "updated_by": "HarshaKanumalla"
}

# Setup logging
logger = logging.getLogger(__name__)

# Get settings
settings = get_settings()

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a hashed password."""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Generate password hash."""
    return pwd_context.hash(password)

async def authenticate_user(email: str, password: str) -> Union[UserInDB, bool]:
    """Authenticate a user with email and password."""
    try:
        logger.info(f"Attempting authentication for email: {email}")
        
        user = await get_user_by_email(email)
        if not user:
            logger.error(f"No user found with email: {email}")
            return False
            
        logger.info(f"Stored hash: {user.hashed_password}")
        logger.info(f"Attempting to verify password: {password}")
        
        # Generate a new hash for comparison
        test_hash = pwd_context.hash(password)
        logger.info(f"Generated test hash: {test_hash}")
        
        verification_result = verify_password(password, user.hashed_password)
        logger.info(f"Password verification result: {verification_result}")
        
        if not verification_result:
            logger.error("Password verification failed")
            return False
            
        logger.info("Authentication successful")
        return user
        
    except Exception as e:
        logger.error(f"Authentication error: {str(e)}")
        logger.exception("Detailed error:")
        return False

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token."""
    try:
        settings = get_settings()
        algorithm = settings.jwt_algorithm  # Explicitly get the algorithm
        logger.info(f"Using algorithm: {algorithm}")  # Add logging
        
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=settings.jwt_expiration)
        
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(
            to_encode, 
            settings.secret_key,
            algorithm=algorithm  # Use the explicitly retrieved algorithm
        )
        return encoded_jwt
    except Exception as e:
        logger.error(f"Token creation error details: {str(e)}")
        logger.error(f"Settings available: {vars(get_settings())}")  # Log available settings
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create access token"
        )

async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    """Get current user from JWT token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token, 
            settings.secret_key, 
            algorithms=[settings.algorithm]
        )
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
        
        token_data = TokenData(
            user_id=user_id,
            email=payload.get("email"),
            role=payload.get("role", Role.USER),
            exp=payload.get("exp")
        )
    except JWTError as e:
        logger.error(f"JWT decode error: {str(e)}")
        raise credentials_exception
    except Exception as e:
        logger.error(f"Token validation error: {str(e)}")
        raise credentials_exception

    user = await get_user_by_id(ObjectId(token_data.user_id))
    if user is None:
        raise credentials_exception
    return user

async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """Get current active user."""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    return current_user

async def get_current_admin_user(current_user: User = Depends(get_current_user)) -> User:
    """Get current admin user."""
    if current_user.role != Role.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    return current_user

# Export functions
__all__ = [
    'verify_password',
    'get_password_hash',
    'authenticate_user',
    'create_access_token',
    'get_current_user',
    'get_current_active_user',
    'get_current_admin_user'
]