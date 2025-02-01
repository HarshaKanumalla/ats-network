# backend/app/services/center/center_service.py

from datetime import datetime
from typing import Dict, Any, List, Optional
import logging
from bson import ObjectId
from fastapi import HTTPException, status

from ...core.exceptions import CenterError
from ...services.location.geolocation_service import geolocation_service
from ...services.s3.s3_service import s3_service
from ...database import get_database
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class CenterManagementService:
    def __init__(self):
        self.db = None
        logger.info("Center management service initialized")

    async def create_center(self, center_data: Dict[str, Any], owner_id: str, documents: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new ATS center with proper validation and document handling."""
        try:
            db = await get_database()

            # Geocode address
            location_data = await geolocation_service.geocode_address(
                address=center_data["address"],
                city=center_data["city"],
                state=center_data["state"],
                pin_code=center_data["pinCode"]
            )

            # Generate center code
            center_code = await self._generate_center_code(center_data["state"])

            # Store documents in S3
            document_urls = {}
            for doc_type, file in documents.items():
                url = await s3_service.upload_document(
                    file=file,
                    folder=f"centers/{center_code}/documents",
                    metadata={
                        "center_code": center_code,
                        "document_type": doc_type
                    }
                )
                document_urls[doc_type] = url

            # Create center record
            center_record = {
                "centerName": center_data["centerName"],
                "centerCode": center_code,
                "address": {
                    "street": center_data["address"],
                    "city": center_data["city"],
                    "district": center_data["district"],
                    "state": center_data["state"],
                    "pinCode": center_data["pinCode"],
                    "coordinates": location_data
                },
                "status": "pending",
                "owner": {
                    "userId": ObjectId(owner_id),
                    "documents": document_urls
                },
                "testingEquipment": [],
                "createdAt": datetime.utcnow(),
                "updatedAt": datetime.utcnow()
            }

            result = await db.centers.insert_one(center_record)
            center_record["_id"] = result.inserted_id

            logger.info(f"Created new ATS center: {center_code}")
            return center_record

        except Exception as e:
            logger.error(f"Center creation error: {str(e)}")
            raise CenterError("Failed to create ATS center")

    async def get_centers_by_role(self, user_id: str, user_role: str) -> List[Dict[str, Any]]:
        """Get centers based on user role with appropriate filtering."""
        try:
            db = await get_database()
            query = {}

            if user_role == "ats_owner":
                # ATS owners see only their center
                query["owner.userId"] = ObjectId(user_id)
            elif user_role == "rto_officer":
                # RTO officers see centers in their jurisdiction
                user_data = await db.users.find_one({"_id": ObjectId(user_id)})
                if user_data and "jurisdiction" in user_data:
                    query["address.district"] = {"$in": user_data["jurisdiction"]}
            elif user_role not in ["transport_commissioner", "additional_commissioner"]:
                # Other roles don't see any centers
                return []

            cursor = db.centers.find(query)
            return await cursor.to_list(None)

        except Exception as e:
            logger.error(f"Center retrieval error: {str(e)}")
            raise CenterError("Failed to retrieve centers")

    async def get_center_details(self, center_id: str, user_id: str, user_role: str) -> Optional[Dict[str, Any]]:
        """Get detailed center information with role-based access control."""
        try:
            db = await get_database()
            center = await db.centers.find_one({"_id": ObjectId(center_id)})

            if not center:
                raise HTTPException(status_code=404, detail="Center not found")

            # Verify access permission
            if not await self._can_access_center(user_id, user_role, center):
                raise HTTPException(status_code=403, detail="Access denied")

            # Remove sensitive information based on role
            if user_role not in ["transport_commissioner", "additional_commissioner"]:
                center.pop("owner", None)
                center.pop("documents", None)

            return center

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Center details retrieval error: {str(e)}")
            raise CenterError("Failed to retrieve center details")

    async def update_center_status(self, center_id: str, status: str, updated_by: str) -> Dict[str, Any]:
        """Update center status with proper validation."""
        try:
            db = await get_database()

            result = await db.centers.find_one_and_update(
                {"_id": ObjectId(center_id)},
                {
                    "$set": {
                        "status": status,
                        "updatedBy": ObjectId(updated_by),
                        "updatedAt": datetime.utcnow()
                    }
                },
                return_document=True
            )

            if not result:
                raise HTTPException(status_code=404, detail="Center not found")

            logger.info(f"Updated status for center {center_id} to {status}")
            return result

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Center status update error: {str(e)}")
            raise CenterError("Failed to update center status")

    async def _generate_center_code(self, state: str) -> str:
        """Generate unique center code."""
        try:
            db = await get_database()
            state_prefix = state[:2].upper()
            
            # Get count of centers in state
            count = await db.centers.count_documents({
                "centerCode": {"$regex": f"^ATS{state_prefix}"}
            })
            
            return f"ATS{state_prefix}{str(count + 1).zfill(4)}"

        except Exception as e:
            logger.error(f"Center code generation error: {str(e)}")
            raise CenterError("Failed to generate center code")

    async def _can_access_center(self, user_id: str, user_role: str, center: Dict[str, Any]) -> bool:
        """Verify if user has access to center."""
        if user_role in ["transport_commissioner", "additional_commissioner"]:
            return True
        elif user_role == "ats_owner":
            return str(center["owner"]["userId"]) == user_id
        elif user_role == "rto_officer":
            try:
                db = await get_database()
                user = await db.users.find_one({"_id": ObjectId(user_id)})
                return center["address"]["district"] in user.get("jurisdiction", [])
            except Exception:
                return False
        return False

center_service = CenterManagementService()