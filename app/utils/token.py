# backend/app/utils/token.py

from datetime import datetime, timedelta
from typing import Optional, Dict
from jose import jwt
from ..config import get_settings

settings = get_settings()

def create_token(data: Dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    
    return jwt.encode(
        to_encode,
        settings.access_token_secret,
        algorithm=settings.token_algorithm
    )

def decode_token(token: str) -> Optional[Dict]:
    try:
        return jwt.decode(
            token,
            settings.access_token_secret,
            algorithms=[settings.token_algorithm]
        )
    except jwt.JWTError:
        return None