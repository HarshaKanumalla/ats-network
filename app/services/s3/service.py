# backend/app/services/s3/service.py

import boto3
from botocore.exceptions import ClientError
from typing import Optional, Dict, Any, BinaryIO, List
import logging
from datetime import datetime
import mimetypes
import hashlib
import asyncio
from fastapi import UploadFile
import aiohttp

from ...core.exceptions import StorageError
from ...database import db_manager
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class S3Service:
    def __init__(self):
        """Initialize S3 service with enhanced configuration."""
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_region
        )
        
        self.bucket_name = settings.s3_bucket_name
        
        # Storage configuration
        self.storage_config = {
            'max_file_size': 10 * 1024 * 1024,  # 10MB
            'chunk_size': 8 * 1024 * 1024,      # 8MB for multipart uploads
            'max_retries': 3,
            'retry_delay': 1,                    # seconds
            'default_expiry': 3600,              # 1 hour for presigned URLs
            'cleanup_threshold': 30              # days for temporary files
        }
        
        # Document organization
        self.folder_structure = {
            'centers': {
                'documents': ['registration', 'licenses', 'certifications'],
                'reports': ['performance', 'compliance', 'maintenance']
            },
            'vehicles': {
                'documents': ['registration', 'insurance', 'fitness'],
                'tests': ['images', 'reports', 'certificates']
            },
            'tests': {
                'reports': ['detailed', 'summary'],
                'data': ['raw', 'processed'],
                'images': ['pre', 'post']
            },
            'users': {
                'documents': ['identity', 'qualifications', 'certifications'],
                'profile': ['images']
            }
        }
        
        # Content type validation
        self.allowed_content_types = {
            'documents': {
                'application/pdf': '.pdf',
                'application/msword': '.doc',
                'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx'
            },
            'images': {
                'image/jpeg': '.jpg',
                'image/png': '.png'
            },
            'reports': {
                'application/pdf': '.pdf',
                'application/vnd.ms-excel': '.xls',
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '.xlsx'
            }
        }
        
        # Initialize storage
        self._ensure_storage_setup()
        logger.info("S3 service initialized with enhanced configuration")

    async def upload_document(
        self,
        file: UploadFile,
        folder: str,
        metadata: Optional[Dict[str, str]] = None,
        content_type: Optional[str] = None
    ) -> str:
        """Upload document with comprehensive validation and organization."""
        try:
            # Validate file
            await self._validate_file(file)
            
            # Generate unique filename
            filename = await self._generate_unique_filename(file.filename)
            key = f"{folder.strip('/')}/{filename}"
            
            # Prepare upload parameters
            upload_args = {
                'Bucket': self.bucket_name,
                'Key': key,
                'ContentType': content_type or file.content_type,
                'ServerSideEncryption': 'AES256'
            }
            
            if metadata:
                upload_args['Metadata'] = self._sanitize_metadata(metadata)
            
            # Handle large file uploads
            if file.size > self.storage_config['chunk_size']:
                url = await self._handle_multipart_upload(file, upload_args)
            else:
                url = await self._handle_single_upload(file, upload_args)
            
            # Log upload
            await self._log_file_operation(
                operation='upload',
                key=key,
                metadata=metadata
            )
            
            return url
            
        except Exception as e:
            logger.error(f"File upload error: {str(e)}")
            raise StorageError(f"Failed to upload file: {str(e)}")

    async def get_document_url(
        self,
        file_key: str,
        expiry: Optional[int] = None,
        download: bool = False
    ) -> str:
        """Generate secure URL for document access."""
        try:
            params = {
                'Bucket': self.bucket_name,
                'Key': file_key
            }
            
            if download:
                params['ResponseContentDisposition'] = 'attachment'
            
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params=params,
                ExpiresIn=expiry or self.storage_config['default_expiry']
            )
            
            await self._log_file_operation(
                operation='access',
                key=file_key
            )
            
            return url
            
        except Exception as e:
            logger.error(f"URL generation error: {str(e)}")
            raise StorageError("Failed to generate document URL")

    async def delete_document(self, file_key: str) -> None:
        """Delete document with proper cleanup."""
        try:
            # Verify file exists
            await self._verify_file_exists(file_key)
            
            # Delete file
            await self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=file_key
            )
            
            # Log deletion
            await self._log_file_operation(
                operation='delete',
                key=file_key
            )
            
            logger.info(f"Successfully deleted file: {file_key}")
            
        except Exception as e:
            logger.error(f"File deletion error: {str(e)}")
            raise StorageError("Failed to delete document")

    async def _handle_multipart_upload(
        self,
        file: UploadFile,
        upload_args: Dict[str, Any]
    ) -> str:
        """Handle large file uploads using multipart upload."""
        try:
            # Initiate multipart upload
            response = await self.s3_client.create_multipart_upload(**upload_args)
            upload_id = response['UploadId']
            
            parts = []
            part_number = 1
            
            while True:
                chunk = await file.read(self.storage_config['chunk_size'])
                if not chunk:
                    break
                
                # Upload part
                response = await self.s3_client.upload_part(
                    Bucket=self.bucket_name,
                    Key=upload_args['Key'],
                    UploadId=upload_id,
                    PartNumber=part_number,
                    Body=chunk
                )
                
                parts.append({
                    'PartNumber': part_number,
                    'ETag': response['ETag']
                })
                
                part_number += 1
            
            # Complete multipart upload
            await self.s3_client.complete_multipart_upload(
                Bucket=self.bucket_name,
                Key=upload_args['Key'],
                UploadId=upload_id,
                MultipartUpload={'Parts': parts}
            )
            
            return await self.get_document_url(upload_args['Key'])
            
        except Exception as e:
            if upload_id:
                await self.s3_client.abort_multipart_upload(
                    Bucket=self.bucket_name,
                    Key=upload_args['Key'],
                    UploadId=upload_id
                )
            raise

    async def _validate_file(self, file: UploadFile) -> None:
        """Validate file with comprehensive checks."""
        if not file.content_type:
            raise StorageError("Missing content type")
            
        # Check file size
        if file.size > self.storage_config['max_file_size']:
            raise StorageError(
                f"File size {file.size} exceeds maximum allowed size"
            )
            
        # Validate content type
        valid_types = []
        for category in self.allowed_content_types.values():
            valid_types.extend(category.keys())
            
        if file.content_type not in valid_types:
            raise StorageError(f"Invalid content type: {file.content_type}")
            
        # Additional security checks
        await self._scan_file_content(file)

    async def _generate_unique_filename(
        self,
        original_filename: str
    ) -> str:
        """Generate unique filename with content hash."""
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        content_hash = hashlib.md5(
            f"{original_filename}{timestamp}".encode()
        ).hexdigest()[:8]
        
        extension = original_filename.split('.')[-1].lower()
        return f"{timestamp}_{content_hash}.{extension}"

    async def _scan_file_content(self, file: UploadFile) -> None:
        """Scan file content for potential security threats."""
        try:
            # Implement virus scanning or content validation
            # This could integrate with virus scanning services
            pass
        except Exception as e:
            logger.error(f"File scanning error: {str(e)}")
            raise StorageError("Failed to scan file content")

    async def _log_file_operation(
        self,
        operation: str,
        key: str,
        metadata: Optional[Dict[str, str]] = None
    ) -> None:
        """Log file operations for auditing."""
        try:
            await db_manager.execute_query(
                collection="file_operations",
                operation="insert_one",
                query={
                    "operation": operation,
                    "file_key": key,
                    "metadata": metadata,
                    "timestamp": datetime.utcnow()
                }
            )
        except Exception as e:
            logger.error(f"Operation logging error: {str(e)}")

    def _sanitize_metadata(self, metadata: Dict[str, str]) -> Dict[str, str]:
        """Sanitize metadata for S3 storage."""
        sanitized = {}
        for key, value in metadata.items():
            # Convert all values to strings and remove special characters
            sanitized[key] = str(value).replace('\n', ' ').strip()
        return sanitized

# Initialize S3 service
s3_service = S3Service()