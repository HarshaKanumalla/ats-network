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
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_region
        )
        
        self.bucket_name = settings.s3_bucket_name
        
        # Enhanced configuration settings
        self.storage_settings = {
            'max_file_size': 10 * 1024 * 1024,  # 10MB
            'default_expiry': 3600,  # 1 hour for presigned URLs
            'cleanup_threshold': 30,  # days for temporary file cleanup
            'chunk_size': 8 * 1024 * 1024,  # 8MB for multipart uploads
            'max_retries': 3
        }
        
        # Valid content types mapping
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
                'application/pdf': '.pdf'
            }
        }
        
        # Initialize storage management
        self._ensure_storage_setup()
        logger.info("S3 service initialized with enhanced configuration")

    async def upload_file(
        self,
        file: UploadFile,
        folder: str,
        file_type: str,
        metadata: Optional[Dict[str, str]] = None,
        max_age: Optional[int] = None
    ) -> str:
        """Upload file with comprehensive validation and error handling."""
        try:
            # Validate file
            await self._validate_file(file, file_type)
            
            # Generate unique filename
            filename = await self._generate_unique_filename(file.filename)
            key = f"{folder.strip('/')}/{filename}"
            
            # Prepare upload parameters
            upload_args = {
                'Bucket': self.bucket_name,
                'Key': key,
                'ContentType': file.content_type,
                'ServerSideEncryption': 'AES256'
            }
            
            if metadata:
                upload_args['Metadata'] = self._sanitize_metadata(metadata)
            
            if max_age:
                upload_args['CacheControl'] = f'max-age={max_age}'

            # Handle large file uploads
            if file.size > self.storage_settings['chunk_size']:
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

    async def get_file_url(
        self,
        file_key: str,
        expiry: Optional[int] = None,
        download: bool = False
    ) -> str:
        """Generate secure URL for file access with custom parameters."""
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
                ExpiresIn=expiry or self.storage_settings['default_expiry']
            )
            
            await self._log_file_operation(
                operation='access',
                key=file_key
            )
            
            return url

        except Exception as e:
            logger.error(f"URL generation error: {str(e)}")
            raise StorageError(f"Failed to generate file URL: {str(e)}")

    async def delete_file(self, file_key: str) -> None:
        """Delete file with proper cleanup and verification."""
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
            raise StorageError(f"Failed to delete file: {str(e)}")

    async def cleanup_temporary_files(self) -> None:
        """Clean up expired temporary files and optimize storage."""
        try:
            cutoff_date = datetime.utcnow() - timedelta(
                days=self.storage_settings['cleanup_threshold']
            )
            
            # List objects to delete
            paginator = self.s3_client.get_paginator('list_objects_v2')
            
            for page in paginator.paginate(Bucket=self.bucket_name):
                for obj in page.get('Contents', []):
                    if (
                        'temp/' in obj['Key'] and 
                        obj['LastModified'] < cutoff_date
                    ):
                        await self.delete_file(obj['Key'])
            
            logger.info("Completed temporary file cleanup")

        except Exception as e:
            logger.error(f"Cleanup operation error: {str(e)}")
            raise StorageError(f"Failed to cleanup temporary files: {str(e)}")

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
                chunk = await file.read(self.storage_settings['chunk_size'])
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
            
            return await self.get_file_url(upload_args['Key'])

        except Exception as e:
            if upload_id:
                await self.s3_client.abort_multipart_upload(
                    Bucket=self.bucket_name,
                    Key=upload_args['Key'],
                    UploadId=upload_id
                )
            raise

    async def _validate_file(
        self,
        file: UploadFile,
        file_type: str
    ) -> None:
        """Validate file size and type with comprehensive checks."""
        if file.content_type not in self.allowed_content_types.get(file_type, {}):
            raise StorageError(
                f"Invalid file type {file.content_type} for {file_type}"
            )

        # Check file size
        if file.size > self.storage_settings['max_file_size']:
            raise StorageError(
                f"File size {file.size} exceeds maximum allowed size"
            )

        # Additional security checks
        await self._scan_file_content(file)

    def _ensure_storage_setup(self) -> None:
        """Ensure S3 bucket exists and has proper configuration."""
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
        except ClientError as e:
            error_code = int(e.response['Error']['Code'])
            if error_code == 404:
                self._create_bucket()
            else:
                raise

    async def _scan_file_content(self, file: UploadFile) -> None:
        """Scan file content for potential security threats."""
        # Implementation for file content scanning would go here
        # This could integrate with virus scanning services or
        # content validation libraries
        pass

# Initialize S3 service
s3_service = S3Service()