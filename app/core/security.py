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

from .exceptions import SecurityError
from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class SecurityManager:
    """Manages core security operations and cryptographic functions."""
    
    def __init__(self):
        """Initialize security manager with configuration."""
        # Password settings
        self.password_min_length = 8
        self.password_max_length = 128
        self.password_min_lowercase = 1
        self.password_min_uppercase = 1
        self.password_min_digits = 1
        self.password_min_special = 1
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
            # Generate encryption key from master key
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

    async def hash_password(self, password: str) -> str:
        """Hash password using bcrypt with salt.
        
        Args:
            password: Plain text password
            
        Returns:
            Hashed password
            
        Raises:
            SecurityError: If hashing fails
        """
        try:
            # Generate salt and hash password
            salt = bcrypt.gensalt(rounds=self.hash_rounds)
            password_hash = bcrypt.hashpw(
                password.encode(),
                salt
            )
            return password_hash.decode()
            
        except Exception as e:
            logger.error(f"Password hashing error: {str(e)}")
            raise SecurityError("Failed to hash password")

    async def verify_password(
        self,
        plain_password: str,
        hashed_password: str
    ) -> bool:
        """Verify password against stored hash.
        
        Args:
            plain_password: Password to verify
            hashed_password: Stored password hash
            
        Returns:
            True if password matches, False otherwise
            
        Raises:
            SecurityError: If verification fails
        """
        try:
            return bcrypt.checkpw(
                plain_password.encode(),
                hashed_password.encode()
            )
        except Exception as e:
            logger.error(f"Password verification error: {str(e)}")
            raise SecurityError("Failed to verify password")

    def validate_password(
        self,
        password: str,
        user_info: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Validate password against security requirements.
        
        Args:
            password: Password to validate
            user_info: Optional user information for additional checks
            
        Returns:
            True if password meets requirements, False otherwise
        """
        try:
            # Check length
            if not (self.password_min_length <= len(password) <= 
                   self.password_max_length):
                return False
            
            # Check character requirements
            if len(re.findall(r'[a-z]', password)) < self.password_min_lowercase:
                return False
            if len(re.findall(r'[A-Z]', password)) < self.password_min_uppercase:
                return False
            if len(re.findall(r'\d', password)) < self.password_min_digits:
                return False
            if len(re.findall(r'[!@#$%^&*(),.?":{}|<>]', password)) < self.password_min_special:
                return False
            
            # Check for common patterns
            if re.search(r'(.)\1{2,}', password):  # Repeated characters
                return False
            if re.search(r'(12345|qwerty|password)', password.lower()):
                return False
            
            # Check against user information if provided
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

    async def encrypt_data(self, data: str) -> str:
        """Encrypt sensitive data.
        
        Args:
            data: Data to encrypt
            
        Returns:
            Encrypted data string
            
        Raises:
            SecurityError: If encryption fails
        """
        try:
            encrypted_data = self.cipher.encrypt(data.encode())
            return encrypted_data.decode()
            
        except Exception as e:
            logger.error(f"Data encryption error: {str(e)}")
            raise SecurityError("Failed to encrypt data")

    async def decrypt_data(self, encrypted_data: str) -> str:
        """Decrypt encrypted data.
        
        Args:
            encrypted_data: Data to decrypt
            
        Returns:
            Decrypted data string
            
        Raises:
            SecurityError: If decryption fails
        """
        try:
            decrypted_data = self.cipher.decrypt(encrypted_data.encode())
            return decrypted_data.decode()
            
        except Exception as e:
            logger.error(f"Data decryption error: {str(e)}")
            raise SecurityError("Failed to decrypt data")

    def generate_secure_token(self, byte_length: Optional[int] = None) -> str:
        """Generate cryptographically secure random token.
        
        Args:
            byte_length: Optional custom token length
            
        Returns:
            Secure random token string
        """
        try:
            token_bytes = secrets.token_bytes(
                byte_length or self.token_bytes
            )
            return base64.urlsafe_b64encode(token_bytes).decode()
            
        except Exception as e:
            logger.error(f"Token generation error: {str(e)}")
            raise SecurityError("Failed to generate secure token")

    async def validate_file_upload(
        self,
        file_content: bytes,
        file_type: str,
        max_size: Optional[int] = None
    ) -> bool:
        """Validate file upload for security.
        
        Args:
            file_content: File content bytes
            file_type: MIME type of file
            max_size: Optional maximum file size
            
        Returns:
            True if file is safe, False otherwise
        """
        try:
            # Check file size
            if max_size and len(file_content) > max_size:
                return False
            
            # Check file type
            allowed_types = {
                'image/jpeg': [b'\xFF\xD8\xFF'],
                'image/png': [b'\x89PNG\r\n\x1a\n'],
                'application/pdf': [b'%PDF-'],
                'application/msword': [b'\xD0\xCF\x11\xE0'],
                'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 
                    [b'PK\x03\x04']
            }
            
            if file_type not in allowed_types:
                return False
            
            # Verify file signature
            file_signatures = allowed_types[file_type]
            return any(file_content.startswith(sig) for sig in file_signatures)
            
        except Exception as e:
            logger.error(f"File validation error: {str(e)}")
            return False

    async def sanitize_input(
        self,
        input_string: str,
        allow_html: bool = False
    ) -> str:
        """Sanitize user input to prevent injection attacks.
        
        Args:
            input_string: Input to sanitize
            allow_html: Whether to allow HTML tags
            
        Returns:
            Sanitized input string
        """
        try:
            if not allow_html:
                # Remove HTML tags
                clean_string = re.sub(r'<[^>]*>', '', input_string)
            else:
                # Allow only specific HTML tags
                allowed_tags = ['b', 'i', 'u', 'p', 'br', 'h1', 'h2', 'h3']
                clean_string = input_string
                for tag in re.findall(r'<[^>]*>', input_string):
                    if not any(f'<{t}>' in tag.lower() or f'</{t}>' in tag.lower() 
                             for t in allowed_tags):
                        clean_string = clean_string.replace(tag, '')
            
            # Remove dangerous characters
            clean_string = re.sub(r'[^\w\s@.,!?-]', '', clean_string)
            
            return clean_string
            
        except Exception as e:
            logger.error(f"Input sanitization error: {str(e)}")
            raise SecurityError("Failed to sanitize input")

    def validate_ip_address(self, ip_address: str) -> bool:
        """Validate IP address format.
        
        Args:
            ip_address: IP address to validate
            
        Returns:
            True if valid IP address, False otherwise
        """
        try:
            # IPv4 validation
            if re.match(r'^(\d{1,3}\.){3}\d{1,3}$', ip_address):
                return all(0 <= int(x) <= 255 for x in ip_address.split('.'))
            
            # IPv6 validation
            if ':' in ip_address:
                hex_parts = ip_address.split(':')
                if len(hex_parts) > 8:
                    return False
                return all(len(part) <= 4 and all(c in '0123456789ABCDEFabcdef' 
                                                 for c in part)
                          for part in hex_parts if part)
            
            return False
            
        except Exception:
            return False

# Initialize security manager
security_manager = SecurityManager()