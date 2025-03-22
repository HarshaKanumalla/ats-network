# backend/app/services/storage/s3_service.py

from typing import Dict, Any, Optional, BinaryIO
import logging
from datetime import datetime
import boto3
from botocore.exceptions import ClientError
import mimetypes
import hashlib
import aioboto3
from pathlib import Path

from ...core.exceptions import StorageError
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class S3StorageService:
    """Enhanced service for managing file storage in AWS S3."""
    
    def __init__(self):
        """Initialize S3 storage service with AWS credentials."""
        self.session = aioboto3.Session(
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION
        )
        
        self.bucket_name = settings.S3_BUCKET_NAME
        
        # Storage configuration
        self.storage_config = {
            'max_file_size': 10 * 1024 * 1024,  # 10MB
            'chunk_size': 8 * 1024 * 1024,      # 8MB for multipart uploads
            'allowed_extensions': {
                'pdf', 'jpg', 'jpeg', 'png', 'doc', 'docx'
            },
            'content_types': {
                'pdf': 'application/pdf',
                'jpg': 'image/jpeg',
                'jpeg': 'image/jpeg',
                'png': 'image/png',
                'doc': 'application/msword',
                'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            }
        }
        
        logger.info("S3 storage service initialized")

    async def upload_document(
        self,
        file: BinaryIO,
        folder: str,
        filename: Optional[str] = None,
        content_type: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None
    ) -> str:
        """Upload document to S3 with proper organization and validation."""
        try:
            # Validate file
            await self._validate_file(file, content_type)
            
            # Generate unique filename
            if not filename:
                filename = await self._generate_unique_filename(
                    getattr(file, 'filename', 'document')
                )
            
            # Construct S3 key
            key = f"{folder.strip('/')}/{filename}"
            
            # Prepare upload parameters
            upload_params = {
                'Bucket': self.bucket_name,
                'Key': key,
                'Body': file,
                'ContentType': content_type or mimetypes.guess_type(filename)[0],
                'Metadata': self._sanitize_metadata(metadata or {}),
                'ServerSideEncryption': 'AES256'
            }
            
            # Upload file
            async with self.session.client('s3') as s3:
                await s3.upload_fileobj(**upload_params)
            
            # Generate URL
            url = f"https://{self.bucket_name}.s3.{settings.AWS_REGION}.amazonaws.com/{key}"
            
            logger.info(f"Uploaded document: {key}")
            return url
            
        except Exception as e:
            logger.error(f"Document upload error: {str(e)}")
            raise StorageError(f"Failed to upload document: {str(e)}")

    async def delete_document(self, file_key: str) -> None:
        """Delete document from S3."""
        try:
            async with self.session.client('s3') as s3:
                await s3.delete_object(
                    Bucket=self.bucket_name,
                    Key=file_key
                )
                
            logger.info(f"Deleted document: {file_key}")
            
        except Exception as e:
            logger.error(f"Document deletion error: {str(e)}")
            raise StorageError(f"Failed to delete document: {str(e)}")

    async def get_document_url(
        self,
        file_key: str,
        expiry: int = 3600
    ) -> str:
        """Generate pre-signed URL for document access."""
        try:
            async with self.session.client('s3') as s3:
                url = await s3.generate_presigned_url(
                    'get_object',
                    Params={
                        'Bucket': self.bucket_name,
                ExpiresIn=expiry
            )
            return url
            
        except Exception as e:
            logger.error(f"URL generation error: {str(e)}")
            raise StorageError("Failed to generate document URL")

    async def _validate_file(
        self,
        file: BinaryIO,
        content_type: Optional[str] = None
    ) -> None:
        """Validate file size and type."""
        try:
            # Check file size
            file.seek(0, 2)  # Seek to end
            size = file.tell()
            file.seek(0)  # Reset position
            
            if size > self.storage_config['max_file_size']:
                raise StorageError(
                    f"File size exceeds maximum allowed size of "
                    f"{self.storage_config['max_file_size'] / (1024 * 1024)}MB"
                )
            
            # Validate content type
            if content_type:
                extension = None
                for ext, mime_type in self.storage_config['content_types'].items():
                    if mime_type == content_type:
                        extension = ext
                        break
                
                if not extension or extension not in self.storage_config['allowed_extensions']:
                    raise StorageError(f"Invalid content type: {content_type}")
                    
        except StorageError:
            raise
        except Exception as e:
            logger.error(f"File validation error: {str(e)}")
            raise StorageError("Failed to validate file")

    async def _generate_unique_filename(
        self,
        original_filename: str
    ) -> str:
        """Generate unique filename with timestamp and hash."""
        try:
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            filename_hash = hashlib.md5(
                f"{original_filename}{timestamp}".encode()
            ).hexdigest()[:8]
            
            extension = Path(original_filename).suffix.lower()
            if not extension:
                raise StorageError("Missing file extension")
                
            if extension[1:] not in self.storage_config['allowed_extensions']:
                raise StorageError(f"Invalid file extension: {extension}")
                
            return f"{timestamp}_{filename_hash}{extension}"
            
        except Exception as e:
            logger.error(f"Filename generation error: {str(e)}")
            raise StorageError("Failed to generate filename")

    def _sanitize_metadata(self, metadata: Dict[str, str]) -> Dict[str, str]:
        """Sanitize metadata for S3 storage."""
        sanitized = {}
        for key, value in metadata.items():
            # Convert all values to strings and remove special characters
            sanitized[key] = str(value).replace('\n', ' ').strip()
        return sanitized

    async def list_documents(
        self,
        folder: str,
        max_keys: int = 1000
    ) -> List[Dict[str, Any]]:
        """List documents in specified folder."""
        try:
            folder = folder.strip('/')
            documents = []
            
            async with self.session.client('s3') as s3:
                paginator = s3.get_paginator('list_objects_v2')
                
                async for page in paginator.paginate(
                    Bucket=self.bucket_name,
                    Prefix=folder,
                    MaxKeys=max_keys
                ):
                    if 'Contents' in page:
                        for obj in page['Contents']:
                            doc = {
                                'key': obj['Key'],
                                'size': obj['Size'],
                                'last_modified': obj['LastModified'],
                                'etag': obj['ETag']
                            }
                            
                            try:
                                response = await s3.head_object(
                                    Bucket=self.bucket_name,
                                    Key=obj['Key']
                                )
                                doc['metadata'] = response.get('Metadata', {})
                                doc['content_type'] = response.get('ContentType')
                            except ClientError:
                                pass
                                
                            documents.append(doc)
                            
            return documents
            
        except Exception as e:
            logger.error(f"Document listing error: {str(e)}")
            raise StorageError("Failed to list documents")

    async def copy_document(
        self,
        source_key: str,
        destination_key: str
    ) -> str:
        """Copy document within S3 bucket."""
        try:
            async with self.session.client('s3') as s3:
                copy_source = {
                    'Bucket': self.bucket_name,
                    'Key': source_key
                }
                
                await s3.copy_object(
                    CopySource=copy_source,
                    Bucket=self.bucket_name,
                    Key=destination_key
                )
                
            return f"https://{self.bucket_name}.s3.{settings.AWS_REGION}.amazonaws.com/{destination_key}"
            
        except Exception as e:
            logger.error(f"Document copy error: {str(e)}")
            raise StorageError("Failed to copy document")

    async def get_document_metadata(
        self,
        file_key: str
    ) -> Dict[str, Any]:
        """Get document metadata from S3."""
        try:
            async with self.session.client('s3') as s3:
                response = await s3.head_object(
                    Bucket=self.bucket_name,
                    Key=file_key
                )
                
                return {
                    'metadata': response.get('Metadata', {}),
                    'content_type': response.get('ContentType'),
                    'content_length': response.get('ContentLength'),
                    'last_modified': response.get('LastModified'),
                    'etag': response.get('ETag')
                }
                
        except Exception as e:
            logger.error(f"Metadata retrieval error: {str(e)}")
            raise StorageError("Failed to get document metadata")

# Initialize S3 storage service
s3_service = S3StorageService()