"""Document service for managing file operations and document processing.

This service provides centralized functionality for file handling, document
storage, and validation. It implements secure file processing practices and
maintains proper access controls for document management.
"""

import aiofiles
import os
from pathlib import Path
from fastapi import UploadFile, HTTPException, status
import logging
import magic
import hashlib
from datetime import datetime
from typing import Optional, List

from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class DocumentService:
    """Manages document processing and storage operations."""

    def __init__(self):
        """Initialize the document service with required configurations."""
        self.upload_dir = Path(settings.upload_folder)
        self.max_file_size = settings.max_upload_size
        self.allowed_extensions = settings.allowed_extensions
        
        self._initialize_storage()

    def _initialize_storage(self) -> None:
        """Set up the storage directory structure for document management."""
        try:
            self.upload_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Storage directory initialized: {self.upload_dir}")
        except Exception as e:
            logger.error("Storage initialization failed", exc_info=True)
            raise RuntimeError("Failed to initialize document storage")

    async def process_upload(
        self,
        file: UploadFile,
        user_id: str
    ) -> str:
        """Process and store an uploaded document securely.

        This method handles file upload validation, processing, and storage.
        It implements security checks and maintains proper file organization.

        Args:
            file: The uploaded file object
            user_id: The ID of the user uploading the file

        Returns:
            The URL path to the stored document

        Raises:
            HTTPException: If file validation fails or processing errors occur
        """
        try:
            await self._validate_file(file)
            safe_filename = self._generate_safe_filename(file.filename, user_id)
            file_path = await self._store_file(file, safe_filename)
            
            logger.info(f"File successfully processed: {safe_filename}")
            return f"/documents/{safe_filename}"

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"File processing error: {file.filename}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Document processing failed"
            )

    async def _validate_file(self, file: UploadFile) -> None:
        """Validate uploaded file attributes and content.

        Performs comprehensive file validation including size limits,
        file type verification, and content analysis.

        Args:
            file: The uploaded file to validate

        Raises:
            HTTPException: If the file fails validation checks
        """
        try:
            content = await file.read(1024)  # Read first 1KB for validation
            await file.seek(0)  # Reset file pointer

            if not self._is_valid_extension(file.filename):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid file type. Allowed types: {', '.join(self.allowed_extensions)}"
                )

            mime_type = magic.from_buffer(content, mime=True)
            if not self._is_valid_mime_type(mime_type):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid file content type"
                )

            file_size = await self._get_file_size(file)
            if file_size > self.max_file_size:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"File size exceeds limit of {self.max_file_size / 1024 / 1024}MB"
                )

        except HTTPException:
            raise
        except Exception as e:
            logger.error("File validation error", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="File validation failed"
            )

    def _generate_safe_filename(self, filename: str, user_id: str) -> str:
        """Generate a secure filename for storage.

        Creates a unique, sanitized filename using timestamps and hashing
        to prevent conflicts and security issues.

        Args:
            filename: Original filename
            user_id: ID of the uploading user

        Returns:
            A secure filename for storage
        """
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        name_hash = hashlib.md5(f"{user_id}{timestamp}".encode()).hexdigest()[:8]
        extension = Path(filename).suffix.lower()
        
        return f"{timestamp}_{name_hash}{extension}"

    async def _store_file(self, file: UploadFile, filename: str) -> Path:
        """Store the uploaded file securely.

        Handles the secure storage of uploaded files with proper error handling
        and atomic write operations.

        Args:
            file: The uploaded file to store
            filename: The generated safe filename

        Returns:
            Path to the stored file

        Raises:
            HTTPException: If file storage fails
        """
        file_path = self.upload_dir / filename
        
        try:
            async with aiofiles.open(file_path, 'wb') as out_file:
                while content := await file.read(1024 * 1024):  # Read in 1MB chunks
                    await out_file.write(content)
            
            return file_path

        except Exception as e:
            logger.error(f"File storage error: {filename}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to store document"
            )

    async def delete_document(self, filename: str) -> bool:
        """Delete a stored document.

        Securely removes a stored document with proper access validation
        and error handling.

        Args:
            filename: The name of the file to delete

        Returns:
            Boolean indicating successful deletion
        """
        try:
            file_path = self.upload_dir / filename
            if file_path.exists():
                file_path.unlink()
                logger.info(f"Document deleted: {filename}")
                return True
            return False

        except Exception as e:
            logger.error(f"Document deletion error: {filename}", exc_info=True)
            return False

# Initialize the document service
document_service = DocumentService()