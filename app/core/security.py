from datetime import datetime, timedelta
import bcrypt
import secrets
import re
import logging
import base64
from typing import Optional, Dict, Any
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from ipaddress import ip_network, ip_address

from .exceptions import SecurityError
from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class SecurityManager:
    """Manages core security operations and cryptographic functions."""
    
    def __init__(self):
        """Initialize security manager with configuration."""
        # Password settings
        self.password_policy = {
            "min_length": 8,
            "max_length": 128,
            "min_lowercase": 1,
            "min_uppercase": 1,
            "min_digits": 1,
            "min_special": 1
        }
        self.password_max_age = timedelta(days=90)
        
        # Hashing settings
        self.hash_rounds = 12
        
        # Encryption settings
        self._initialize_encryption()
        
        # Token settings
        self.token_bytes = 32
        
        logger.info("Security manager initialized with enhanced security settings")

    def _initialize_encryption(self) -> None:
        """Initialize encryption key and cipher."""
        try:
            if not isinstance(settings.ENCRYPTION_SALT, str) or not settings.ENCRYPTION_SALT:
                raise SecurityError("ENCRYPTION_SALT must be a non-empty string")
            if not isinstance(settings.MASTER_KEY, str) or not settings.MASTER_KEY:
                raise SecurityError("MASTER_KEY must be a non-empty string")
            
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=settings.ENCRYPTION_SALT.encode(),
                iterations=100000
            )
            key = base64.urlsafe_b64encode(
                kdf.derive(settings.MASTER_KEY.encode())
            )
            self.cipher = Fernet(key)
            
        except Exception as e:
            logger.error(f"Encryption initialization error: {str(e)}")
            raise SecurityError("Failed to initialize encryption")

    def rotate_encryption_key(self, new_master_key: str) -> None:
        """Rotate the encryption key."""
        try:
            if not isinstance(new_master_key, str) or not new_master_key:
                raise SecurityError("New master key must be a non-empty string")
            old_master_key = settings.MASTER_KEY
            settings.MASTER_KEY = new_master_key
            self._initialize_encryption()
            logger.info("Encryption key rotated successfully")
        except Exception as e:
            settings.MASTER_KEY = old_master_key  # Rollback
            logger.error(f"Key rotation error: {str(e)}")
            raise SecurityError("Failed to rotate encryption key")

    async def hash_password(self, password: str) -> str:
        """Hash password using bcrypt with salt."""
        try:
            salt = bcrypt.gensalt(rounds=self.hash_rounds)
            password_hash = bcrypt.hashpw(password.encode(), salt)
            logger.info("Password hashed successfully")
            return password_hash.decode()
        except Exception as e:
            logger.error(f"Password hashing error: {str(e)}")
            raise SecurityError("Failed to hash password")

    async def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify password against stored hash."""
        try:
            return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())
        except Exception as e:
            logger.error(f"Password verification error: {str(e)}")
            raise SecurityError("Failed to verify password")

    def validate_password(self, password: str, user_info: Optional[Dict[str, Any]] = None) -> bool:
        """Validate password against security requirements."""
        try:
            policy = self.password_policy
            if not (policy["min_length"] <= len(password) <= policy["max_length"]):
                return False
            if len(re.findall(r'[a-z]', password)) < policy["min_lowercase"]:
                return False
            if len(re.findall(r'[A-Z]', password)) < policy["min_uppercase"]:
                return False
            if len(re.findall(r'\d', password)) < policy["min_digits"]:
                return False
            if len(re.findall(r'[!@#$%^&*(),.?":{}|<>]', password)) < policy["min_special"]:
                return False
            if re.search(r'(.)\1{2,}', password):  # Repeated characters
                return False
            if re.search(r'(12345|qwerty|password)', password.lower()):
                return False
            if user_info:
                user_terms = [
                    user_info.get('email', '').split('@')[0].lower(),
                    user_info.get('username', '').lower(),
                    user_info.get('first_name', '').lower(),
                    user_info.get('last_name', '').lower()
                ]
                if any(term in password.lower() for term in user_terms if term):
                    return False
            return True
        except Exception as e:
            logger.error(f"Password validation error: {str(e)}")
            return False

    async def validate_file_upload(self, file_content: bytes, file_type: str, max_size: Optional[int] = None) -> bool:
        """Validate file upload for security."""
        try:
            if max_size and len(file_content) > max_size:
                return False
            allowed_types = {
                'image/jpeg': [b'\xFF\xD8\xFF'],
                'image/png': [b'\x89PNG\r\n\x1a\n'],
                'application/pdf': [b'%PDF-'],
                'application/msword': [b'\xD0\xCF\x11\xE0'],
                'application/vnd.openxmlformats-officedocument.wordprocessingml.document': [b'PK\x03\x04']
            }
            if file_type not in allowed_types:
                return False
            file_signatures = allowed_types[file_type]
            return any(file_content.startswith(sig) for sig in file_signatures)
        except Exception as e:
            logger.error(f"File validation error: {str(e)}")
            return False

    def validate_ip_address(self, ip_address: str) -> bool:
        """Validate IP address or CIDR format."""
        try:
            ip_address(ip_address)  # Validate single IP
            return True
        except ValueError:
            try:
                ip_network(ip_address, strict=False)  # Validate CIDR
                return True
            except ValueError:
                return False

    def generate_secure_token(self, byte_length: Optional[int] = None) -> str:
        """Generate cryptographically secure random token."""
        try:
            token_bytes = secrets.token_bytes(byte_length or self.token_bytes)
            return base64.urlsafe_b64encode(token_bytes).decode()
        except Exception as e:
            logger.error(f"Token generation error: {str(e)}")
            raise SecurityError("Failed to generate secure token")

    def generate_secure_token_with_expiry(self, byte_length: Optional[int] = None, expiry_minutes: int = 60) -> Dict[str, Any]:
        """Generate a secure token with an expiry timestamp."""
        try:
            token = self.generate_secure_token(byte_length)
            expiry = datetime.utcnow() + timedelta(minutes=expiry_minutes)
            return {"token": token, "expiry": expiry.isoformat()}
        except Exception as e:
            logger.error(f"Token generation with expiry error: {str(e)}")
            raise SecurityError("Failed to generate secure token with expiry")

# Initialize security manager
security_manager = SecurityManager()