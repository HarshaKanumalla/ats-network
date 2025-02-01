# backend/app/utils/file_utils.py

from typing import Optional, List, Dict
import os
import mimetypes
import hashlib
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class FileUtils:
    """Utility functions for file handling."""
    
    ALLOWED_MIME_TYPES = {
        'application/pdf': '.pdf',
        'image/jpeg': '.jpg',
        'image/png': '.png',
        'application/msword': '.doc',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx'
    }
    
    @staticmethod
    def get_safe_filename(original_filename: str, prefix: str = '') -> str:
        """Generate a safe filename with timestamp."""
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        file_hash = hashlib.md5(f"{original_filename}{timestamp}".encode()).hexdigest()[:8]
        extension = os.path.splitext(original_filename)[1].lower()
        
        return f"{prefix}_{timestamp}_{file_hash}{extension}"

    @staticmethod
    def validate_mime_type(content_type: str) -> bool:
        """Validate if the content type is allowed."""
        return content_type in FileUtils.ALLOWED_MIME_TYPES