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
    def get_safe_filename(original_filename: str, prefix: str = '') -> Optional[str]:
        """
        Generate a safe filename with a timestamp and hash.
        
        Args:
            original_filename (str): The original filename.
            prefix (str): An optional prefix for the filename.
        
        Returns:
            Optional[str]: A safe filename, or None if the input is invalid.
        """
        if not original_filename or '.' not in original_filename:
            logger.error("Invalid filename provided: %s", original_filename)
            return None
        
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        file_hash = hashlib.md5(f"{original_filename}{timestamp}".encode()).hexdigest()[:8]
        extension = os.path.splitext(original_filename)[1].lower()
        
        return f"{prefix}_{timestamp}_{file_hash}{extension}"

    @staticmethod
    def validate_mime_type(content_type: str) -> bool:
        """
        Validate if the content type is allowed.
        
        Args:
            content_type (str): The MIME type to validate.
        
        Returns:
            bool: True if the MIME type is allowed, False otherwise.
        """
        if content_type in FileUtils.ALLOWED_MIME_TYPES:
            return True
        logger.warning("Unsupported MIME type: %s", content_type)
        return False

    @staticmethod
    def get_mime_type(file_path: str) -> Optional[str]:
        """
        Determine the MIME type of a file.
        
        Args:
            file_path (str): The path to the file.
        
        Returns:
            Optional[str]: The MIME type of the file, or None if it cannot be determined.
        """
        mime_type, _ = mimetypes.guess_type(file_path)
        if not mime_type:
            logger.warning("Could not determine MIME type for file: %s", file_path)
        return mime_type

    @staticmethod
    def file_exists(file_path: str) -> bool:
        """
        Check if a file exists.
        
        Args:
            file_path (str): The path to the file.
        
        Returns:
            bool: True if the file exists, False otherwise.
        """
        exists = os.path.isfile(file_path)
        if not exists:
            logger.warning("File does not exist: %s", file_path)
        return exists

    @staticmethod
    def calculate_checksum(file_path: str, algorithm: str = 'sha256') -> Optional[str]:
        """
        Calculate the checksum of a file.
        
        Args:
            file_path (str): The path to the file.
            algorithm (str): The hashing algorithm to use (default is 'sha256').
        
        Returns:
            Optional[str]: The checksum of the file, or None if the file cannot be read.
        """
        if not FileUtils.file_exists(file_path):
            return None
        
        try:
            hash_func = hashlib.new(algorithm)
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b''):
                    hash_func.update(chunk)
            return hash_func.hexdigest()
        except Exception as e:
            logger.error("Error calculating checksum for file %s: %s", file_path, str(e))
            return None

    @staticmethod
    def delete_file(file_path: str) -> bool:
        """
        Delete a file safely.
        
        Args:
            file_path (str): The path to the file.
        
        Returns:
            bool: True if the file was deleted successfully, False otherwise.
        """
        try:
            if FileUtils.file_exists(file_path):
                os.remove(file_path)
                logger.info("File deleted successfully: %s", file_path)
                return True
            return False
        except Exception as e:
            logger.error("Error deleting file %s: %s", file_path, str(e))
            return False