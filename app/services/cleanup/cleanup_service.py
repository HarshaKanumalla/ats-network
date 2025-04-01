from typing import Dict, Any, List, Optional
import logging
from datetime import datetime, timedelta
import asyncio
from bson import ObjectId

from ...core.exceptions import CleanupError
from ...database import get_database
from ...config import get_settings
from ...services.s3 import s3_service
from ...services.notification import notification_service

logger = logging.getLogger(__name__)
settings = get_settings()

class CleanupService:
    """Service for handling system cleanup and maintenance tasks."""
    
    def __init__(self):
        """Initialize cleanup service with configuration."""
        self.db = None
        
        # Cleanup intervals
        self.intervals = {
            'expired_sessions': timedelta(hours=1),
            'temporary_files': timedelta(days=1),
            'old_notifications': timedelta(days=7),
            'audit_logs': timedelta(days=30),
            'test_results': timedelta(days=90)
        }
        
        # Retention periods
        self.retention_periods = {
            'sessions': timedelta(days=1),
            'notifications': timedelta(days=30),
            'audit_logs': timedelta(days=90),
            'test_results': timedelta(days=365),
            'temporary_files': timedelta(hours=24)
        }
        
        logger.info("Cleanup service initialized")

    async def _get_database(self):
        """Get database connection with error handling."""
        try:
            return await get_database()
        except Exception as e:
            logger.error(f"Database connection error: {str(e)}")
            raise CleanupError("Failed to connect to the database")

    async def _retry_s3_operation(self, operation: callable, *args, retries: int = 3, **kwargs):
        """Retry S3 operation in case of transient failures."""
        for attempt in range(retries):
            try:
                return await operation(*args, **kwargs)
            except Exception as e:
                if attempt < retries - 1:
                    logger.warning(f"S3 operation failed, retrying... ({attempt + 1}/{retries})")
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                else:
                    logger.error(f"S3 operation failed after {retries} retries: {str(e)}")
                    raise CleanupError("S3 operation failed")

    async def start_cleanup_tasks(self) -> None:
        """Start all cleanup tasks with concurrency control."""
        try:
            tasks = [
                asyncio.create_task(self._cleanup_expired_sessions()),
                asyncio.create_task(self._cleanup_temporary_files()),
                asyncio.create_task(self._cleanup_old_notifications()),
                asyncio.create_task(self._cleanup_audit_logs()),
                asyncio.create_task(self._cleanup_test_results())
            ]
            
            for task in asyncio.as_completed(tasks):
                try:
                    await task
                except Exception as e:
                    logger.error(f"Cleanup task failed: {str(e)}")
        except Exception as e:
            logger.error(f"Cleanup tasks startup error: {str(e)}")
            raise CleanupError("Failed to start cleanup tasks")

    async def _cleanup_expired_sessions(self) -> None:
        """Clean up expired user sessions periodically."""
        while True:
            try:
                db = await self._get_database()
                current_time = datetime.utcnow()
                
                # Find expired sessions
                expired_sessions = await db.sessions.find({
                    'expiresAt': {'$lt': current_time},
                    'active': True
                }).to_list(None)
                
                for session in expired_sessions:
                    # Invalidate session
                    await db.sessions.update_one(
                        {'_id': session['_id']},
                        {
                            '$set': {
                                'active': False,
                                'invalidatedAt': current_time,
                                'invalidationReason': 'expired'
                            }
                        }
                    )
                    
                    # Log session invalidation
                    await db.auditLogs.insert_one({
                        'action': 'session_expired',
                        'userId': session['userId'],
                        'sessionId': session['_id'],
                        'timestamp': current_time
                    })
                
                logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")
                await asyncio.sleep(self.intervals['expired_sessions'].total_seconds())
                
            except Exception as e:
                logger.error(f"Session cleanup error: {str(e)}")
                await asyncio.sleep(300)  # Retry after 5 minutes

    async def _cleanup_temporary_files(self) -> None:
        """Clean up temporary files from S3 storage."""
        while True:
            try:
                db = await self._get_database()
                current_time = datetime.utcnow()
                
                # Get list of temporary files from S3
                temp_files = await self._retry_s3_operation(
                    s3_service.list_documents,
                    folder='temp',
                    max_keys=1000
                )
                
                for file in temp_files:
                    # Check if file has expired
                    if file.get('last_modified') + self.retention_periods['temporary_files'] < current_time:
                        # Delete from S3
                        await self._retry_s3_operation(s3_service.delete_document, file['key'])
                        
                        # Log deletion
                        await db.auditLogs.insert_one({
                            'action': 'temp_file_deleted',
                            'fileKey': file['key'],
                            'timestamp': current_time
                        })
                
                logger.info(f"Cleaned up {len(temp_files)} temporary files")
                await asyncio.sleep(self.intervals['temporary_files'].total_seconds())
                
            except Exception as e:
                logger.error(f"Temporary files cleanup error: {str(e)}")
                await asyncio.sleep(300)

    async def _cleanup_old_notifications(self) -> None:
        """Clean up old notifications based on retention policy."""
        while True:
            try:
                db = await self._get_database()
                current_time = datetime.utcnow()
                retention_cutoff = current_time - self.retention_periods['notifications']
                
                # Archive old notifications
                old_notifications = await db.notifications.find({
                    'createdAt': {'$lt': retention_cutoff},
                    'archived': {'$ne': True}
                }).to_list(None)
                
                if old_notifications:
                    # Create archive record
                    archive_data = {
                        'type': 'notifications',
                        'period': {
                            'start': min(n['createdAt'] for n in old_notifications),
                            'end': max(n['createdAt'] for n in old_notifications)
                        },
                        'count': len(old_notifications),
                        'data': old_notifications,
                        'createdAt': current_time
                    }
                    
                    await db.archives.insert_one(archive_data)
                    
                    # Mark notifications as archived
                    notification_ids = [n['_id'] for n in old_notifications]
                    await db.notifications.update_many(
                        {'_id': {'$in': notification_ids}},
                        {
                            '$set': {
                                'archived': True,
                                'archivedAt': current_time
                            }
                        }
                    )
                
                logger.info(f"Archived {len(old_notifications)} old notifications")
                await asyncio.sleep(self.intervals['old_notifications'].total_seconds())
                
            except Exception as e:
                logger.error(f"Notifications cleanup error: {str(e)}")
                await asyncio.sleep(300)

    async def _cleanup_audit_logs(self) -> None:
        """Archive and clean up old audit logs."""
        while True:
            try:
                db = await self._get_database()
                current_time = datetime.utcnow()
                retention_cutoff = current_time - self.retention_periods['audit_logs']
                
                # Find old audit logs
                old_logs = await db.auditLogs.find({
                    'timestamp': {'$lt': retention_cutoff},
                    'archived': {'$ne': True}
                }).to_list(None)
                
                if old_logs:
                    # Create archive record
                    archive_data = {
                        'type': 'audit_logs',
                        'period': {
                            'start': min(log['timestamp'] for log in old_logs),
                            'end': max(log['timestamp'] for log in old_logs)
                        },
                        'count': len(old_logs),
                        'data': old_logs,
                        'createdAt': current_time
                    }
                    
                    await db.archives.insert_one(archive_data)
                    
                    # Mark logs as archived
                    log_ids = [log['_id'] for log in old_logs]
                    await db.auditLogs.update_many(
                        {'_id': {'$in': log_ids}},
                        {
                            '$set': {
                                'archived': True,
                                'archivedAt': current_time
                            }
                        }
                    )
                
                logger.info(f"Archived {len(old_logs)} audit logs")
                await asyncio.sleep(self.intervals['audit_logs'].total_seconds())
                
            except Exception as e:
                logger.error(f"Audit logs cleanup error: {str(e)}")
                await asyncio.sleep(300)

    async def _cleanup_test_results(self) -> None:
        """Archive old test results and related data."""
        while True:
            try:
                db = await self._get_database()
                current_time = datetime.utcnow()
                retention_cutoff = current_time - self.retention_periods['test_results']
                
                # Find old test sessions
                old_sessions = await db.testSessions.find({
                    'testDate': {'$lt': retention_cutoff},
                    'archived': {'$ne': True}
                }).to_list(None)
                
                if old_sessions:
                    for session in old_sessions:
                        # Archive test data
                        archive_data = {
                            'type': 'test_session',
                            'sessionId': session['_id'],
                            'testDate': session['testDate'],
                            'vehicleId': session['vehicleId'],
                            'centerId': session['centerId'],
                            'data': session,
                            'createdAt': current_time
                        }
                        
                        await db.archives.insert_one(archive_data)
                        
                        # Archive related files
                        if 'documents' in session:
                            for doc in session['documents']:
                                new_key = f"archives/tests/{session['_id']}/{doc['filename']}"
                                await self._retry_s3_operation(
                                    s3_service.copy_document,
                                    doc['key'],
                                    new_key
                                )
                                await self._retry_s3_operation(s3_service.delete_document, doc['key'])
                        
                        # Mark session as archived
                        await db.testSessions.update_one(
                            {'_id': session['_id']},
                            {
                                '$set': {
                                    'archived': True,
                                    'archivedAt': current_time
                                }
                            }
                        )
                
                logger.info(f"Archived {len(old_sessions)} test sessions")
                await asyncio.sleep(self.intervals['test_results'].total_seconds())
                
            except Exception as e:
                logger.error(f"Test results cleanup error: {str(e)}")
                await asyncio.sleep(300)

    async def cleanup_failed_uploads(self) -> None:
        """Clean up incomplete and failed file uploads."""
        try:
            # Get incomplete multipart uploads
            incomplete_uploads = await self._retry_s3_operation(s3_service.list_multipart_uploads)
            
            for upload in incomplete_uploads:
                if upload['Initiated'] + timedelta(days=1) < datetime.utcnow():
                    await self._retry_s3_operation(
                        s3_service.abort_multipart_upload,
                        upload['Key'],
                        upload['UploadId']
                    )
            
            logger.info(f"Cleaned up {len(incomplete_uploads)} incomplete uploads")
            
        except Exception as e:
            logger.error(f"Failed uploads cleanup error: {str(e)}")
            raise CleanupError("Failed to clean up incomplete uploads")

    async def cleanup_orphaned_files(self) -> None:
        """Clean up orphaned files in storage."""
        try:
            db = await self._get_database()
            
            # Get all document references from database
            referenced_files = set()
            
            # Check user documents
            async for user in db.users.find({}, {'documents': 1}):
                if 'documents' in user:
                    for doc in user['documents']:
                        referenced_files.add(doc['fileUrl'])
            
            # Check center documents
            async for center in db.centers.find({}, {'documents': 1}):
                if 'documents' in center:
                    for doc in center['documents']:
                        referenced_files.add(doc['fileUrl'])
            
            # Check test session documents
            async for session in db.testSessions.find({}, {'documents': 1}):
                if 'documents' in session:
                    for doc in session['documents']:
                        referenced_files.add(doc['fileUrl'])
            
            # Get all files from S3
            all_files = await self._retry_s3_operation(s3_service.list_all_documents)
            
            # Find orphaned files
            orphaned_files = [
                file for file in all_files
                if file['url'] not in referenced_files
            ]
            
            # Delete orphaned files
            for file in orphaned_files:
                await self._retry_s3_operation(s3_service.delete_document, file['key'])
                
                # Log deletion
                await db.auditLogs.insert_one({
                    'action': 'orphaned_file_deleted',
                    'fileKey': file['key'],
                    'timestamp': datetime.utcnow()
                })
            
            logger.info(f"Cleaned up {len(orphaned_files)} orphaned files")
            
        except Exception as e:
            logger.error(f"Orphaned files cleanup error: {str(e)}")
            raise CleanupError("Failed to clean up orphaned files")

# Initialize cleanup service
cleanup_service = CleanupService()