from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import logging
from bson import ObjectId
import hashlib
import json
import asyncio

from ...core.exceptions import DocumentError
from ...services.s3.s3_service import s3_service
from ...services.notification.notification_service import notification_service
from ...database import get_database, database_transaction
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class DocumentService:
    """Service for managing document operations and lifecycle."""
    
    def __init__(self):
        """Initialize document service with enhanced capabilities."""
        self.db = None
        
        # Document type configurations
        self.document_types = {
            "vehicle_registration": {
                "required": True,
                "expiry_check": True,
                "allowed_formats": ["pdf"],
                "max_size_mb": 5,
                "retention_period_days": 3650,  # 10 years
                "verification_required": True
            },
            "fitness_certificate": {
                "required": True,
                "expiry_check": True,
                "allowed_formats": ["pdf"],
                "max_size_mb": 5,
                "retention_period_days": 365,
                "verification_required": True
            },
            "insurance_document": {
                "required": True,
                "expiry_check": True,
                "allowed_formats": ["pdf"],
                "max_size_mb": 5,
                "retention_period_days": 365,
                "verification_required": True
            },
            "center_license": {
                "required": True,
                "expiry_check": True,
                "allowed_formats": ["pdf"],
                "max_size_mb": 10,
                "retention_period_days": 1825,  # 5 years
                "verification_required": True
            },
            "equipment_certification": {
                "required": True,
                "expiry_check": True,
                "allowed_formats": ["pdf"],
                "max_size_mb": 5,
                "retention_period_days": 365,
                "verification_required": True
            },
            "test_report": {
                "required": False,
                "expiry_check": False,
                "allowed_formats": ["pdf"],
                "max_size_mb": 10,
                "retention_period_days": 3650,
                "verification_required": False
            }
        }
        
        # Digital signature requirements
        self.signature_requirements = {
            "vehicle_registration": ["rto_officer"],
            "fitness_certificate": ["ats_admin", "rto_officer"],
            "center_license": ["transport_commissioner"],
            "equipment_certification": ["ats_admin"]
        }
        
        logger.info("Document service initialized")

    async def _get_database(self):
        """Get database connection with error handling."""
        try:
            return await get_database()
        except Exception as e:
            logger.error(f"Database connection error: {str(e)}")
            raise DocumentError("Failed to connect to the database")

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
                    raise DocumentError("S3 operation failed")

    async def process_document(
        self,
        document_type: str,
        file: Any,
        metadata: Dict[str, Any],
        owner_id: str
    ) -> Dict[str, Any]:
        """Process and store new document with validation."""
        try:
            # Validate document type
            doc_config = self.document_types.get(document_type)
            if not doc_config:
                raise DocumentError(f"Invalid document type: {document_type}")

            # Validate file
            await self._validate_document(file, doc_config)

            # Generate unique document ID
            document_id = await self._generate_document_id(
                document_type,
                metadata
            )

            # Store file in S3
            file_url = await self._retry_s3_operation(
                s3_service.upload_document,
                file=file,
                folder=f"documents/{document_type}/{document_id}",
                metadata={
                    **metadata,
                    "document_id": document_id,
                    "uploaded_by": owner_id,
                    "upload_date": datetime.utcnow().isoformat()
                }
            )

            # Create document record
            document_record = {
                "document_id": document_id,
                "document_type": document_type,
                "file_url": file_url,
                "metadata": metadata,
                "owner_id": ObjectId(owner_id),
                "status": "pending_verification" if doc_config["verification_required"] else "active",
                "version": 1,
                "expiry_date": metadata.get("expiry_date"),
                "verification_status": {
                    "verified": False,
                    "verified_by": None,
                    "verification_date": None,
                    "verification_notes": None
                },
                "signatures": [],
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }

            # Store record in database
            async with database_transaction() as session:
                db = await self._get_database()
                await db.documents.insert_one(document_record, session=session)

                # Create document history entry
                await self._create_history_entry(
                    document_id=document_id,
                    action="created",
                    details=document_record,
                    performed_by=owner_id,
                    session=session
                )

            # Schedule expiry check if required
            if doc_config["expiry_check"] and metadata.get("expiry_date"):
                await self._schedule_expiry_check(
                    document_id,
                    metadata["expiry_date"]
                )

            logger.info(f"Processed document: {document_id}")
            return document_record

        except Exception as e:
            logger.error(f"Document processing error: {str(e)}")
            raise DocumentError(f"Failed to process document: {str(e)}")

    async def verify_document(
        self,
        document_id: str,
        verifier_id: str,
        verification_status: str,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """Verify document with proper authorization."""
        try:
            db = await self._get_database()
            
            # Get document record
            document = await db.documents.find_one({
                "document_id": document_id
            })
            if not document:
                raise DocumentError("Document not found")

            # Verify authorization
            if not await self._verify_authorization(
                verifier_id,
                document["document_type"],
                "verify"
            ):
                raise DocumentError("Unauthorized to verify document")

            # Update verification status
            verification_update = {
                "verification_status": {
                    "verified": verification_status == "approved",
                    "verified_by": ObjectId(verifier_id),
                    "verification_date": datetime.utcnow(),
                    "verification_notes": notes
                },
                "status": verification_status,
                "updated_at": datetime.utcnow()
            }

            result = await db.documents.find_one_and_update(
                {"document_id": document_id},
                {"$set": verification_update},
                return_document=True
            )

            # Create history entry
            await self._create_history_entry(
                document_id=document_id,
                action="verified",
                details=verification_update,
                performed_by=verifier_id
            )

            # Send notification
            await self._send_verification_notification(
                document,
                verification_status,
                notes
            )

            logger.info(
                f"Document {document_id} verified with status: {verification_status}"
            )
            return result

        except Exception as e:
            logger.error(f"Document verification error: {str(e)}")
            raise DocumentError("Failed to verify document")

    async def add_digital_signature(
        self,
        document_id: str,
        signer_id: str,
        signature_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Add digital signature to document."""
        try:
            db = await self._get_database()
            
            # Get document record
            document = await db.documents.find_one({
                "document_id": document_id
            })
            if not document:
                raise DocumentError("Document not found")

            # Verify signature authorization
            if not await self._verify_authorization(
                signer_id,
                document["document_type"],
                "sign"
            ):
                raise DocumentError("Unauthorized to sign document")

            # Create signature record
            signature_record = {
                "signer_id": ObjectId(signer_id),
                "signature_data": signature_data,
                "timestamp": datetime.utcnow(),
                "signature_hash": self._generate_signature_hash(
                    signer_id,
                    signature_data
                )
            }

            # Update document with signature
            result = await db.documents.find_one_and_update(
                {"document_id": document_id},
                {
                    "$push": {"signatures": signature_record},
                    "$set": {
                        "updated_at": datetime.utcnow()
                    }
                },
                return_document=True
            )

            # Create history entry
            await self._create_history_entry(
                document_id=document_id,
                action="signed",
                details=signature_record,
                performed_by=signer_id
            )

            logger.info(f"Digital signature added to document: {document_id}")
            return result

        except Exception as e:
            logger.error(f"Digital signature error: {str(e)}")
            raise DocumentError("Failed to add digital signature")

    async def _validate_document(
        self,
        file: Any,
        config: Dict[str, Any]
    ) -> None:
        """Validate document against type-specific requirements."""
        try:
            # Check file format
            file_extension = file.filename.split('.')[-1].lower()
            if file_extension not in config["allowed_formats"]:
                raise DocumentError(
                    f"Invalid file format. Allowed formats: "
                    f"{', '.join(config['allowed_formats'])}"
                )

            # Check file size
            file_size_mb = len(file.file.read()) / (1024 * 1024)
            if file_size_mb > config["max_size_mb"]:
                raise DocumentError(
                    f"File size exceeds maximum allowed size of "
                    f"{config['max_size_mb']}MB"
                )

            # Reset file pointer
            file.file.seek(0)

            # Additional security checks
            await self._scan_document_content(file)

        except Exception as e:
            logger.error(f"Document validation error: {str(e)}")
            raise DocumentError(f"Document validation failed: {str(e)}")

    async def _scan_document_content(self, file: Any) -> None:
        """Scan document content for security threats."""
        try:
            # Implementation for content scanning
            # This could integrate with virus scanning or content validation services
            pass
        except Exception as e:
            logger.error(f"Document scanning error: {str(e)}")
            raise DocumentError("Failed to scan document content")

    def _generate_signature_hash(
        self,
        signer_id: str,
        signature_data: Dict[str, Any]
    ) -> str:
        """Generate unique hash for digital signature."""
        signature_string = f"{signer_id}_{json.dumps(signature_data, sort_keys=True)}"
        return hashlib.sha256(signature_string.encode()).hexdigest()

    async def _create_history_entry(
        self,
        document_id: str,
        action: str,
        details: Dict[str, Any],
        performed_by: str,
        session: Optional[Any] = None
    ) -> None:
        """Create document history entry."""
        try:
            db = await self._get_database()
            history_entry = {
                "document_id": document_id,
                "action": action,
                "details": details,
                "performed_by": ObjectId(performed_by),
                "timestamp": datetime.utcnow()
            }

            await db.document_history.insert_one(history_entry, session=session)

        except Exception as e:
            logger.error(f"History entry creation error: {str(e)}")
            raise DocumentError("Failed to create document history entry")

    async def _schedule_expiry_check(self, document_id: str, expiry_date: str) -> None:
        """Schedule a task to handle document expiry."""
        try:
            expiry_datetime = datetime.strptime(expiry_date, "%Y-%m-%d")
            if expiry_datetime < datetime.utcnow():
                raise DocumentError("Expiry date is in the past")

            # Schedule expiry notification
            await notification_service.schedule_notification(
                {
                    "document_id": document_id,
                    "expiry_date": expiry_datetime,
                    "message": f"Document {document_id} is about to expire."
                }
            )
            logger.info(f"Scheduled expiry check for document: {document_id}")
        except Exception as e:
            logger.error(f"Expiry check scheduling error: {str(e)}")
            raise DocumentError("Failed to schedule expiry check")

    async def _verify_authorization(
        self, user_id: str, document_type: str, action: str
    ) -> bool:
        """Verify if the user is authorized to perform the action on the document."""
        try:
            allowed_roles = self.signature_requirements.get(document_type, [])
            db = await self._get_database()
            user = await db.users.find_one({"_id": ObjectId(user_id)})
            if not user or user.get("role") not in allowed_roles:
                return False
            return True
        except Exception as e:
            logger.error(f"Authorization verification error: {str(e)}")
            return False

# Initialize document service
document_service = DocumentService()