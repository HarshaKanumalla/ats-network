from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import logging
from bson import ObjectId

from ...core.exceptions import CenterError
from ...models.center import CenterCreate, CenterUpdate, CenterEquipment
from ...services.location import location_service
from ...services.s3 import s3_service
from ...services.notification import notification_service
from ...database import get_database, database_transaction
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class CenterManagementService:
    """Enhanced service for managing ATS centers and equipment."""
    
    def __init__(self):
        """Initialize center management service."""
        self.db = None
        
        # Equipment maintenance settings
        self.maintenance_intervals = {
            "speed_test": timedelta(days=90),   # 3 months
            "brake_test": timedelta(days=60),   # 2 months
            "noise_test": timedelta(days=180),  # 6 months
            "headlight_test": timedelta(days=90),
            "axle_test": timedelta(days=90)
        }
        
        # Calibration requirements
        self.calibration_thresholds = {
            "speed_test": {
                "interval_days": 180,
                "tolerance": 0.5,
                "required_points": 5
            },
            "brake_test": {
                "interval_days": 90,
                "force_tolerance": 2.0,
                "balance_tolerance": 1.0
            },
            "noise_test": {
                "interval_days": 365,
                "db_tolerance": 0.5
            }
        }
        
        # Document requirements
        self.required_documents = {
            "business_license": {
                "required": True,
                "expires": True,
                "formats": ["pdf"]
            },
            "equipment_certification": {
                "required": True,
                "expires": True,
                "formats": ["pdf"]
            },
            "staff_certifications": {
                "required": True,
                "expires": True,
                "formats": ["pdf"]
            }
        }
        
        logger.info("Center management service initialized")

    async def create_center(
        self,
        center_data: CenterCreate,
        owner_id: str,
        documents: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create a new ATS center with enhanced validation."""
        async with database_transaction() as session:
            try:
                db = await get_database()
                
                # Verify center code uniqueness
                if await db.centers.find_one({"centerCode": center_data.center_code}):
                    raise CenterError("Center code already exists")
                
                # Process and validate location
                location_data = await location_service.geocode_address(
                    address=center_data.address,
                    city=center_data.city,
                    state=center_data.state,
                    pin_code=center_data.pin_code
                )
                
                if not location_data:
                    raise CenterError("Failed to validate center location")
                
                # Process and store documents
                document_urls = await self._process_center_documents(
                    center_data.center_code,
                    documents
                )
                
                # Create center record
                center_doc = {
                    "centerName": center_data.center_name,
                    "centerCode": center_data.center_code,
                    "address": {
                        "street": center_data.address,
                        "city": center_data.city,
                        "district": center_data.district,
                        "state": center_data.state,
                        "pinCode": center_data.pin_code,
                        "coordinates": location_data
                    },
                    "status": "pending",
                    "owner": {
                        "userId": ObjectId(owner_id),
                        "documents": document_urls
                    },
                    "testingEquipment": [],
                    "operatingHours": center_data.operating_hours,
                    "contactInfo": {
                        "phone": center_data.contact_phone,
                        "email": center_data.contact_email,
                        "website": center_data.website
                    },
                    "capacity": {
                        "maxTestsPerDay": center_data.max_tests_per_day,
                        "simultaneousTests": center_data.simultaneous_tests
                    },
                    "statistics": {
                        "totalTests": 0,
                        "testsToday": 0,
                        "lastTestDate": None
                    },
                    "createdAt": datetime.utcnow(),
                    "updatedAt": datetime.utcnow()
                }
                
                # Insert center record
                result = await db.centers.insert_one(center_doc, session=session)
                center_doc["_id"] = result.inserted_id
                
                # Set up maintenance schedules
                await self._setup_maintenance_schedules(str(result.inserted_id))
                
                # Send notifications
                await self._send_registration_notifications(center_doc)
                
                logger.info(f"Created new ATS center: {center_data.center_code}")
                return center_doc
                
            except Exception as e:
                logger.error(f"Center creation error: {str(e)}")
                raise CenterError(f"Failed to create center: {str(e)}")

    async def _process_center_documents(
        self,
        center_code: str,
        documents: Dict[str, Any]
    ) -> Dict[str, str]:
        """Process and store center documentation."""
        try:
            document_urls = {}
            
            # Verify required documents
            for doc_type, config in self.required_documents.items():
                if config["required"] and doc_type not in documents:
                    raise CenterError(f"Missing required document: {doc_type}")
            
            # Process each document
            for doc_type, doc_data in documents.items():
                # Validate format
                if not self._validate_document_format(
                    doc_data["file"],
                    self.required_documents[doc_type]["formats"]
                ):
                    raise CenterError(f"Invalid format for {doc_type}")
                
                # Upload to S3
                url = await s3_service.upload_document(
                    file=doc_data["file"],
                    folder=f"centers/{center_code}/documents",
                    metadata={
                        "center_code": center_code,
                        "document_type": doc_type,
                        "uploaded_at": datetime.utcnow().isoformat()
                    }
                )
                
                document_urls[doc_type] = {
                    "url": url,
                    "expiryDate": doc_data.get("expiryDate"),
                    "verificationStatus": "pending",
                    "uploadedAt": datetime.utcnow()
                }
            
            return document_urls
            
        except Exception as e:
            logger.error(f"Document processing error: {str(e)}")
            raise CenterError("Failed to process center documents")

    async def update_equipment(
        self,
        center_id: str,
        equipment: CenterEquipment,
        updated_by: str
    ) -> Dict[str, Any]:
        """Update center equipment with calibration tracking."""
        try:
            db = await get_database()
            
            # Validate equipment data
            if not self._validate_equipment_data(equipment):
                raise CenterError("Invalid equipment data")
            
            # Calculate next calibration date
            calibration_config = self.calibration_thresholds.get(
                equipment.equipment_type
            )
            if not calibration_config:
                raise CenterError("Invalid equipment type")
            
            next_calibration = datetime.utcnow() + timedelta(
                days=calibration_config["interval_days"]
            )
            
            # Update equipment record
            result = await db.centers.find_one_and_update(
                {"_id": ObjectId(center_id)},
                {
                    "$push": {
                        "testingEquipment": {
                            "type": equipment.equipment_type,
                            "serialNumber": equipment.serial_number,
                            "manufacturer": equipment.manufacturer,
                            "model": equipment.model,
                            "lastCalibration": datetime.utcnow(),
                            "nextCalibration": next_calibration,
                            "calibrationData": equipment.calibration_data,
                            "status": "active",
                            "addedBy": ObjectId(updated_by),
                            "addedAt": datetime.utcnow()
                        }
                    },
                    "$set": {
                        "updatedAt": datetime.utcnow(),
                        "updatedBy": ObjectId(updated_by)
                    }
                },
                return_document=True
            )
            
            # Schedule calibration reminder
            await self._schedule_calibration_reminder(
                center_id,
                equipment.equipment_type,
                next_calibration
            )
            
            logger.info(
                f"Updated equipment for center {center_id}: "
                f"{equipment.equipment_type}"
            )
            return result
            
        except Exception as e:
            logger.error(f"Equipment update error: {str(e)}")
            raise CenterError("Failed to update equipment")

    async def get_centers_by_role(
        self,
        user_id: str,
        user_role: str,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Get centers based on user role with role-based filtering."""
        try:
            db = await get_database()
            query = filters or {}
            
            # Apply role-based filtering
            if user_role == "ats_owner":
                # ATS owners see only their center
                query["owner.userId"] = ObjectId(user_id)
            elif user_role == "rto_officer":
                # RTO officers see centers in their jurisdiction
                user = await db.users.find_one({"_id": ObjectId(user_id)})
                if user and "jurisdiction" in user:
                    query["address.district"] = {"$in": user["jurisdiction"]}
            elif user_role not in ["transport_commissioner", "additional_commissioner"]:
                return []  # Other roles don't see any centers
            
            # Get centers with statistics
            pipeline = [
                {"$match": query},
                {
                    "$lookup": {
                        "from": "testSessions",
                        "localField": "_id",
                        "foreignField": "centerId",
                        "as": "testSessions"
                    }
                },
                {
                    "$addFields": {
                        "statistics": {
                            "totalTests": {"$size": "$testSessions"},
                            "recentTests": {
                                "$size": {
                                    "$filter": {
                                        "input": "$testSessions",
                                        "cond": {
                                            "$gte": [
                                                "$$this.testDate",
                                                {
                                                    "$subtract": [
                                                        "$$NOW",
                                                        1000 * 60 * 60 * 24 * 30
                                                    ]
                                                }
                                            ]
                                        }
                                    }
                                }
                            }
                        }
                    }
                },
                {
                    "$project": {
                        "testSessions": 0  # Remove detailed test data
                    }
                }
            ]
            
            return await db.centers.aggregate(pipeline).to_list(None)
            
        except Exception as e:
            logger.error(f"Center retrieval error: {str(e)}")
            raise CenterError("Failed to retrieve centers")

    async def _setup_maintenance_schedules(self, center_id: str) -> None:
        """Set up maintenance schedules for center equipment."""
        try:
            for equipment_type, interval in self.maintenance_intervals.items():
                next_maintenance = datetime.utcnow() + interval
                await self._schedule_maintenance(
                    center_id,
                    equipment_type,
                    next_maintenance
                )
                
        except Exception as e:
            logger.error(f"Maintenance scheduling error: {str(e)}")

    async def _schedule_calibration_reminder(
        self,
        center_id: str,
        equipment_type: str,
        next_calibration: datetime
    ) -> None:
        """Schedule a reminder for equipment calibration."""
        try:
            reminder_data = {
                "centerId": center_id,
                "equipmentType": equipment_type,
                "reminderDate": next_calibration,
                "message": f"Calibration due for {equipment_type} equipment."
            }
            await notification_service.schedule_reminder(reminder_data)
            logger.info(f"Scheduled calibration reminder for {equipment_type} in center {center_id}")
        except Exception as e:
            logger.error(f"Calibration reminder scheduling error: {str(e)}")

    async def _send_registration_notifications(self, center_doc: Dict[str, Any]) -> None:
        """Send notifications for center registration."""
        try:
            notification_data = {
                "title": "New Center Registration",
                "message": f"Center {center_doc['centerName']} has been registered and is pending approval.",
                "recipients": [center_doc["owner"]["userId"]]
            }
            await notification_service.send_notification(notification_data)
            logger.info(f"Sent registration notification for center {center_doc['centerCode']}")
        except Exception as e:
            logger.error(f"Notification sending error: {str(e)}")

    def _validate_equipment_data(self, equipment: CenterEquipment) -> bool:
        """Validate equipment data against requirements."""
        try:
            if not equipment.equipment_type or not equipment.serial_number:
                return False
            if not equipment.manufacturer or not equipment.model:
                return False
            if not isinstance(equipment.calibration_data, dict):
                return False
            return True
        except Exception as e:
            logger.error(f"Equipment validation error: {str(e)}")
            return False

    def _validate_document_format(self, file: Any, allowed_formats: List[str]) -> bool:
        """Validate the format of a document."""
        try:
            file_extension = file.filename.split(".")[-1].lower()
            return file_extension in allowed_formats
        except Exception as e:
            logger.error(f"Document format validation error: {str(e)}")
            return False

# Initialize center management service
center_service = CenterManagementService()