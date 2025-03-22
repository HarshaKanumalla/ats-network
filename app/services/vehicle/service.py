# backend/app/services/vehicle/service.py

from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import logging
from bson import ObjectId

from ...core.exceptions import VehicleError
from ...models.vehicle import Vehicle, VehicleCreate, VehicleUpdate
from ...services.s3 import s3_service
from ...services.notification import notification_service
from ...database import get_database, database_transaction
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class VehicleManagementService:
    """Enhanced service for managing vehicle operations and records."""
    
    def __init__(self):
        """Initialize vehicle management service."""
        self.db = None
        
        # Document verification settings
        self.document_types = {
            "registration": {
                "required": True,
                "expiry_check": True,
                "allowed_formats": ["pdf", "jpg", "png"]
            },
            "insurance": {
                "required": True,
                "expiry_check": True,
                "allowed_formats": ["pdf"]
            },
            "fitness": {
                "required": False,
                "expiry_check": True,
                "allowed_formats": ["pdf"]
            }
        }
        
        # Test validity periods (in days)
        self.test_validity = {
            "commercial": 180,  # 6 months
            "private": 365,    # 1 year
            "transport": 90    # 3 months
        }
        
        logger.info("Vehicle management service initialized")

    async def register_vehicle(
        self,
        vehicle_data: VehicleCreate,
        documents: Dict[str, Any],
        center_id: str
    ) -> Dict[str, Any]:
        """Register a new vehicle with enhanced validation and document handling."""
        async with database_transaction() as session:
            try:
                db = await get_database()
                
                # Validate registration number format
                if not self._validate_registration_number(
                    vehicle_data.registration_number
                ):
                    raise VehicleError("Invalid registration number format")
                
                # Check for existing vehicle
                existing = await db.vehicles.find_one({
                    "registrationNumber": vehicle_data.registration_number
                })
                if existing:
                    raise VehicleError("Vehicle already registered")
                
                # Process and verify documents
                document_verification = await self._process_vehicle_documents(
                    vehicle_data.registration_number,
                    documents
                )
                
                # Create vehicle record
                vehicle_doc = {
                    "registrationNumber": vehicle_data.registration_number,
                    "vehicleType": vehicle_data.vehicle_type,
                    "manufacturingYear": vehicle_data.manufacturing_year,
                    "ownerInfo": {
                        "name": vehicle_data.owner_name,
                        "contact": vehicle_data.owner_contact,
                        "address": vehicle_data.owner_address,
                        "email": vehicle_data.owner_email
                    },
                    "documentVerification": document_verification,
                    "registeredCenter": ObjectId(center_id),
                    "lastTestDate": None,
                    "nextTestDue": None,
                    "testHistory": [],
                    "status": "active",
                    "createdAt": datetime.utcnow(),
                    "updatedAt": datetime.utcnow()
                }
                
                # Insert vehicle record
                result = await db.vehicles.insert_one(
                    vehicle_doc,
                    session=session
                )
                vehicle_doc["_id"] = result.inserted_id
                
                # Send notifications
                await self._send_registration_notifications(
                    vehicle_doc,
                    center_id
                )
                
                # Schedule document expiry checks
                await self._schedule_document_checks(str(result.inserted_id))
                
                logger.info(
                    f"Registered vehicle: {vehicle_data.registration_number}"
                )
                return vehicle_doc
                
            except Exception as e:
                logger.error(f"Vehicle registration error: {str(e)}")
                raise VehicleError(f"Failed to register vehicle: {str(e)}")

    async def _process_vehicle_documents(
        self,
        registration_number: str,
        documents: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process and validate vehicle documents with enhanced security."""
        try:
            doc_verification = {}
            
            # Verify required documents
            for doc_type, config in self.document_types.items():
                if config["required"] and doc_type not in documents:
                    raise VehicleError(f"Missing required document: {doc_type}")
            
            # Process each document
            for doc_type, doc_data in documents.items():
                # Validate document format
                if not self._validate_document_format(
                    doc_data["file"],
                    self.document_types[doc_type]["allowed_formats"]
                ):
                    raise VehicleError(
                        f"Invalid format for {doc_type}"
                    )
                
                # Upload to S3
                url = await s3_service.upload_document(
                    file=doc_data["file"],
                    folder=f"vehicles/{registration_number}/documents",
                    metadata={
                        "registration_number": registration_number,
                        "document_type": doc_type,
                        "uploaded_at": datetime.utcnow().isoformat()
                    }
                )
                
                # Create verification record
                doc_verification[doc_type] = {
                    "documentNumber": doc_data.get("documentNumber"),
                    "expiryDate": doc_data.get("expiryDate"),
                    "verificationStatus": "pending",
                    "documentUrl": url,
                    "uploadedAt": datetime.utcnow()
                }
                
                # Validate expiry date if required
                if (self.document_types[doc_type]["expiry_check"] and
                    doc_data.get("expiryDate")):
                    if doc_data["expiryDate"] <= datetime.utcnow():
                        raise VehicleError(
                            f"Document {doc_type} has expired"
                        )
            
            return doc_verification
            
        except Exception as e:
            logger.error(f"Document processing error: {str(e)}")
            raise VehicleError(f"Failed to process documents: {str(e)}")

    async def update_vehicle_documents(
        self,
        registration_number: str,
        new_documents: Dict[str, Any],
        updated_by: str
    ) -> Dict[str, Any]:
        """Update vehicle documentation with version tracking."""
        try:
            db = await get_database()
            
            # Get current vehicle record
            vehicle = await db.vehicles.find_one({
                "registrationNumber": registration_number
            })
            if not vehicle:
                raise VehicleError("Vehicle not found")
            
            # Process new documents
            new_verification = await self._process_vehicle_documents(
                registration_number,
                new_documents
            )
            
            # Archive old documents
            archived_docs = []
            for doc_type, doc_info in vehicle["documentVerification"].items():
                if doc_type in new_verification:
                    archived_docs.append({
                        "type": doc_type,
                        "url": doc_info["documentUrl"],
                        "archivedAt": datetime.utcnow()
                    })
            
            # Update document verification
            result = await db.vehicles.find_one_and_update(
                {"registrationNumber": registration_number},
                {
                    "$set": {
                        "documentVerification": new_verification,
                        "updatedAt": datetime.utcnow(),
                        "updatedBy": ObjectId(updated_by)
                    },
                    "$push": {
                        "documentHistory": {
                            "$each": archived_docs
                        }
                    }
                },
                return_document=True
            )
            
            # Send notification
            await notification_service.send_notification(
                recipient_id=updated_by,
                title="Vehicle Documents Updated",
                message=f"Documents updated for vehicle {registration_number}",
                notification_type="document_update"
            )
            
            logger.info(f"Updated documents for vehicle: {registration_number}")
            return result
            
        except Exception as e:
            logger.error(f"Document update error: {str(e)}")
            raise VehicleError("Failed to update documents")

    async def add_test_record(
        self,
        registration_number: str,
        test_session_id: str
    ) -> Dict[str, Any]:
        """Add test session record to vehicle history."""
        try:
            db = await get_database()
            
            # Get test session details
            test_session = await db.testSessions.find_one({
                "_id": ObjectId(test_session_id)
            })
            if not test_session:
                raise VehicleError("Test session not found")
            
            # Calculate next test due date
            vehicle = await db.vehicles.find_one({
                "registrationNumber": registration_number
            })
            if not vehicle:
                raise VehicleError("Vehicle not found")
            
            validity_days = self.test_validity.get(
                vehicle["vehicleType"],
                365  # Default to 1 year
            )
            next_test_due = datetime.utcnow() + timedelta(days=validity_days)
            
            # Update vehicle record
            result = await db.vehicles.find_one_and_update(
                {"registrationNumber": registration_number},
                {
                    "$push": {
                        "testHistory": {
                            "sessionId": test_session["_id"],
                            "testDate": test_session["testDate"],
                            "centerId": test_session["atsCenterId"],
                            "status": test_session["status"],
                            "certificateNumber": test_session.get(
                                "certificateNumber"
                            )
                        }
                    },
                    "$set": {
                        "lastTestDate": test_session["testDate"],
                        "nextTestDue": next_test_due,
                        "updatedAt": datetime.utcnow()
                    }
                },
                return_document=True
            )
            
            # Send notifications
            await self._send_test_notifications(result, test_session)
            
            logger.info(f"Added test record for vehicle: {registration_number}")
            return result
            
        except Exception as e:
            logger.error(f"Test record error: {str(e)}")
            raise VehicleError("Failed to add test record")

    def _validate_registration_number(self, number: str) -> bool:
        """Validate vehicle registration number format."""
        import re
        pattern = r'^[A-Z]{2}[0-9]{2}[A-Z]{1,2}[0-9]{4}$'
        return bool(re.match(pattern, number))

    async def _schedule_document_checks(self, vehicle_id: str) -> None:
        """Schedule periodic document expiry checks."""
        try:
            # Implementation for scheduling document checks
            pass
        except Exception as e:
            logger.error(f"Document check scheduling error: {str(e)}")

    async def _send_registration_notifications(
        self,
        vehicle_doc: Dict[str, Any],
        center_id: str
    ) -> None:
        """Send notifications for vehicle registration."""
        try:
            # Notify owner
            await notification_service.send_notification(
                recipient_id=vehicle_doc["ownerInfo"]["email"],
                title="Vehicle Registration Successful",
                message=(
                    f"Your vehicle {vehicle_doc['registrationNumber']} "
                    "has been registered successfully"
                ),
                notification_type="vehicle_registration"
            )
            
            # Notify center
            await notification_service.send_notification(
                recipient_id=center_id,
                title="New Vehicle Registration",
                message=(
                    f"Vehicle {vehicle_doc['registrationNumber']} "
                    "has been registered at your center"
                ),
                notification_type="center_notification"
            )
        except Exception as e:
            logger.error(f"Notification error: {str(e)}")

# Initialize vehicle management service
vehicle_service = VehicleManagementService()