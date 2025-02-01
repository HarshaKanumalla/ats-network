# backend/app/services/vehicle/service.py

"""
Service for managing vehicle records, documentation, and test histories.
Handles vehicle registration, document verification, and test tracking.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import logging
from bson import ObjectId

from ...core.exceptions import VehicleError
from ...models.vehicle import Vehicle, VehicleCreate, VehicleUpdate
from ...services.s3 import s3_service
from ...database import get_database
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class VehicleManagementService:
   """Service for managing vehicle operations and records."""
   
   def __init__(self):
       """Initialize vehicle management service."""
       self.db = None
       logger.info("Vehicle management service initialized")

   async def register_vehicle(
       self,
       vehicle_data: VehicleCreate,
       documents: Dict[str, Any],
       center_id: str
   ) -> Dict[str, Any]:
       """Register a new vehicle for testing.
       
       Handles complete vehicle registration including:
       1. Document validation and storage
       2. Vehicle record creation
       3. Document verification status tracking
       """
       try:
           db = await get_database()
           
           # Validate registration number format
           if not self._validate_registration_number(vehicle_data.registration_number):
               raise VehicleError("Invalid vehicle registration number format")
           
           # Check for existing vehicle
           existing = await db.vehicles.find_one({
               "registrationNumber": vehicle_data.registration_number
           })
           if existing:
               raise VehicleError("Vehicle already registered")
           
           # Process and store documents
           document_verification = await self._process_vehicle_documents(
               vehicle_data.registration_number,
               documents
           )
           
           # Prepare vehicle document
           vehicle_doc = {
               "registrationNumber": vehicle_data.registration_number,
               "vehicleType": vehicle_data.vehicle_type,
               "manufacturingYear": vehicle_data.manufacturing_year,
               "ownerInfo": {
                   "name": vehicle_data.owner_name,
                   "contact": vehicle_data.owner_contact,
                   "address": vehicle_data.owner_address
               },
               "documentVerification": document_verification,
               "registeredCenter": ObjectId(center_id),
               "lastTestDate": None,
               "nextTestDue": None,
               "testHistory": [],
               "createdAt": datetime.utcnow(),
               "updatedAt": datetime.utcnow()
           }
           
           # Insert vehicle record
           result = await db.vehicles.insert_one(vehicle_doc)
           vehicle_doc["_id"] = result.inserted_id
           
           logger.info(f"Registered new vehicle: {vehicle_data.registration_number}")
           return vehicle_doc
           
       except Exception as e:
           logger.error(f"Vehicle registration error: {str(e)}")
           raise VehicleError("Failed to register vehicle")

   async def _process_vehicle_documents(
       self,
       registration_number: str,
       documents: Dict[str, Any]
   ) -> Dict[str, Any]:
       """Process and store vehicle documentation."""
       try:
           doc_verification = {}
           
           for doc_type, doc_data in documents.items():
               url = await s3_service.upload_document(
                   file=doc_data["file"],
                   folder=f"vehicles/{registration_number}/documents",
                   metadata={
                       "registration_number": registration_number,
                       "document_type": doc_type
                   }
               )
               
               doc_verification[doc_type] = {
                   "documentNumber": doc_data.get("documentNumber"),
                   "expiryDate": doc_data.get("expiryDate"),
                   "verificationStatus": "pending",
                   "documentUrl": url,
                   "uploadedAt": datetime.utcnow()
               }
           
           return doc_verification
           
       except Exception as e:
           logger.error(f"Document processing error: {str(e)}")
           raise VehicleError("Failed to process vehicle documents")

   async def get_vehicle_by_registration(
       self,
       registration_number: str
   ) -> Optional[Dict[str, Any]]:
       """Get vehicle details by registration number."""
       try:
           db = await get_database()
           
           # Get vehicle with test history
           pipeline = [
               {"$match": {"registrationNumber": registration_number}},
               {
                   "$lookup": {
                       "from": "testSessions",
                       "localField": "testHistory",
                       "foreignField": "_id",
                       "as": "testDetails"
                   }
               }
           ]
           
           result = await db.vehicles.aggregate(pipeline).to_list(1)
           return result[0] if result else None
           
       except Exception as e:
           logger.error(f"Error fetching vehicle: {str(e)}")
           raise VehicleError("Failed to fetch vehicle details")

   async def update_vehicle_documents(
       self,
       registration_number: str,
       documents: Dict[str, Any],
       updated_by: str
   ) -> Dict[str, Any]:
       """Update vehicle documentation."""
       try:
           db = await get_database()
           
           # Process new documents
           doc_verification = await self._process_vehicle_documents(
               registration_number,
               documents
           )
           
           # Update document verification
           result = await db.vehicles.find_one_and_update(
               {"registrationNumber": registration_number},
               {
                   "$set": {
                       "documentVerification": doc_verification,
                       "updatedAt": datetime.utcnow(),
                       "updatedBy": ObjectId(updated_by)
                   }
               },
               return_document=True
           )
           
           if not result:
               raise VehicleError("Vehicle not found")
           
           logger.info(f"Updated documents for vehicle: {registration_number}")
           return result
           
       except Exception as e:
           logger.error(f"Document update error: {str(e)}")
           raise VehicleError("Failed to update vehicle documents")

   async def add_test_record(
       self,
       registration_number: str,
       test_session_id: str
   ) -> Dict[str, Any]:
       """Add test session to vehicle history."""
       try:
           db = await get_database()
           
           # Update vehicle test history
           result = await db.vehicles.find_one_and_update(
               {"registrationNumber": registration_number},
               {
                   "$push": {
                       "testHistory": ObjectId(test_session_id)
                   },
                   "$set": {
                       "lastTestDate": datetime.utcnow(),
                       "nextTestDue": datetime.utcnow() + settings.test_validity_period,
                       "updatedAt": datetime.utcnow()
                   }
               },
               return_document=True
           )
           
           if not result:
               raise VehicleError("Vehicle not found")
           
           logger.info(f"Added test record for vehicle: {registration_number}")
           return result
           
       except Exception as e:
           logger.error(f"Test record error: {str(e)}")
           raise VehicleError("Failed to add test record")

   async def get_vehicles_by_center(
       self,
       center_id: str,
       filter_options: Optional[Dict[str, Any]] = None
   ) -> List[Dict[str, Any]]:
       """Get vehicles registered at specific center."""
       try:
           db = await get_database()
           
           # Build query
           query = {"registeredCenter": ObjectId(center_id)}
           if filter_options:
               query.update(filter_options)
           
           cursor = db.vehicles.find(query)
           return await cursor.to_list(None)
           
       except Exception as e:
           logger.error(f"Center vehicles error: {str(e)}")
           raise VehicleError("Failed to fetch center vehicles")

   def _validate_registration_number(self, number: str) -> bool:
       """Validate vehicle registration number format."""
       import re
       pattern = r'^[A-Z]{2}[0-9]{2}[A-Z]{1,2}[0-9]{4}$'
       return bool(re.match(pattern, number))

# Initialize vehicle management service
vehicle_service = VehicleManagementService()