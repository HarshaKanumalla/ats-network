# backend/app/core/database/validator.py

from typing import Dict, Any, List, Optional
from datetime import datetime
import re
from bson import ObjectId
import logging
from pydantic import BaseModel, ValidationError as PydanticValidationError

from ...core.exceptions import ValidationError as CustomValidationError, SchemaError
from ...models.center import CenterCreate, CenterUpdate
from ...models.test import TestSession, TestUpdate
from ...models.user import UserCreate, UserUpdate
from ...models.vehicle import VehicleCreate, VehicleUpdate
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class DatabaseValidator:
    """Manages data validation and schema enforcement for database operations."""

    def __init__(self):
        """Initialize database validator with validation rules."""
        self.validation_schemas = {
            "users": {
                "create": UserCreate,
                "update": UserUpdate,
                "required": ["email", "role", "status"],
                "unique": ["email"],
                "validators": {
                    "email": self._validate_email,
                    "phone": self._validate_phone,
                    "password": self._validate_password
                }
            },
            "centers": {
                "create": CenterCreate,
                "update": CenterUpdate,
                "required": ["centerName", "centerCode", "address", "status"],
                "unique": ["centerCode"],
                "validators": {
                    "centerCode": self._validate_center_code,
                    "pinCode": self._validate_pin_code,
                    "coordinates": self._validate_coordinates
                }
            },
            "testSessions": {
                "create": TestSession,
                "update": TestUpdate,
                "required": ["vehicleId", "centerId", "sessionCode", "status"],
                "validators": {
                    "sessionCode": self._validate_session_code,
                    "testResults": self._validate_test_results
                }
            },
            "vehicles": {
                "create": VehicleCreate,
                "update": VehicleUpdate,
                "required": ["registrationNumber", "vehicleType", "manufacturingYear"],
                "unique": ["registrationNumber"],
                "validators": {
                    "registrationNumber": self._validate_registration_number,
                    "manufacturingYear": self._validate_manufacturing_year
                }
            }
        }

        self.type_validators = {
            "string": str,
            "integer": int,
            "float": float,
            "boolean": bool,
            "datetime": datetime,
            "object_id": ObjectId,
            "array": list,
            "object": dict
        }

        logger.info("Database validator initialized with validation schemas")

    async def validate_document(
        self,
        collection: str,
        document: Dict[str, Any],
        operation: str = "create",
        db=None
    ) -> None:
        """Validate document against schema and rules."""
        try:
            schema = self.validation_schemas.get(collection)
            if not schema:
                raise SchemaError(f"No validation schema defined for collection: {collection}")

            # Validate required fields
            if operation == "create":
                missing_fields = [
                    field for field in schema["required"]
                    if field not in document
                ]
                if missing_fields:
                    raise CustomValidationError(f"Missing required fields: {', '.join(missing_fields)}")

            # Apply Pydantic model validation
            model_class = schema.get(operation)
            if model_class:
                try:
                    model_class(**document)
                except PydanticValidationError as e:
                    raise CustomValidationError(f"Model validation failed: {str(e)}")

            # Apply field validators
            for field, validator in schema.get("validators", {}).items():
                if field in document:
                    if not await validator(document[field]):
                        raise CustomValidationError(f"Validation failed for field: {field}")

            # Check unique fields
            if db:
                await self._validate_unique_fields(collection, document, db)

            # Validate field types
            await self._validate_field_types(document)

            # Validate custom business rules
            await self._validate_business_rules(collection, document, operation)

        except CustomValidationError:
            raise
        except Exception as e:
            logger.error(f"Document validation error: {str(e)}")
            raise CustomValidationError(f"Document validation failed: {str(e)}")

    async def validate_update(
        self,
        collection: str,
        update_query: Dict[str, Any],
        update_data: Dict[str, Any]
    ) -> None:
        """Validate update operation parameters."""
        try:
            schema = self.validation_schemas.get(collection)
            if not schema:
                return

            # Validate update operators
            for operator, value in update_data.items():
                if not operator.startswith('$'):
                    raise CustomValidationError("Invalid update operator format")

                if operator == '$set':
                    await self.validate_document(
                        collection,
                        value,
                        operation="update"
                    )
                elif operator in ['$push', '$addToSet']:
                    await self._validate_array_operation(collection, value)
                elif operator == '$inc':
                    await self._validate_increment_operation(collection, value)
                elif operator == '$unset':
                    for field in value.keys():
                        if field not in schema["required"]:
                            raise CustomValidationError(f"Cannot unset required field: {field}")
                elif operator == '$rename':
                    for old_field, new_field in value.items():
                        if old_field not in schema["required"] or new_field not in schema["required"]:
                            raise CustomValidationError(f"Cannot rename unknown fields: {old_field} -> {new_field}")

            # Validate business rules for update
            await self._validate_update_rules(
                collection,
                update_query,
                update_data
            )

        except CustomValidationError:
            raise
        except Exception as e:
            logger.error(f"Update validation error: {str(e)}")
            raise CustomValidationError("Update validation failed")

    async def _validate_unique_fields(self, collection: str, document: Dict[str, Any], db) -> None:
        """Validate unique fields in the document."""
        schema = self.validation_schemas.get(collection)
        unique_fields = schema.get("unique", [])
        for field in unique_fields:
            if field in document:
                existing = await db[collection].find_one({field: document[field]})
                if existing:
                    raise CustomValidationError(f"Field '{field}' must be unique. Value '{document[field]}' already exists.")

    async def _validate_field_types(self, document: Dict[str, Any]) -> None:
        """Validate field data types."""
        for field, value in document.items():
            if value is not None:
                expected_type = self.type_validators.get(type(value).__name__)
                if expected_type and not isinstance(value, expected_type):
                    raise CustomValidationError(
                        f"Invalid type for field {field}. "
                        f"Expected {expected_type.__name__}, got {type(value).__name__}"
                    )

    async def _validate_business_rules(
        self,
        collection: str,
        document: Dict[str, Any],
        operation: str
    ) -> None:
        """Validate business-specific rules."""
        if collection == "testSessions":
            await self._validate_test_session_rules(document, operation)
        elif collection == "centers":
            await self._validate_center_rules(document, operation)
        elif collection == "vehicles":
            await self._validate_vehicle_rules(document, operation)

    async def _validate_test_session_rules(
        self,
        document: Dict[str, Any],
        operation: str
    ) -> None:
        """Validate test session specific rules."""
        if operation == "create":
            if "scheduledTime" in document:
                scheduled_time = document["scheduledTime"]
                if scheduled_time < datetime.utcnow():
                    raise CustomValidationError("Test cannot be scheduled in the past")

        elif operation == "update":
            if "status" in document:
                valid_transitions = {
                    "scheduled": ["in_progress", "cancelled"],
                    "in_progress": ["completed", "failed"],
                    "completed": [],
                    "failed": []
                }
                current_status = document.get("currentStatus")
                new_status = document["status"]

                if current_status and new_status not in valid_transitions.get(current_status, []):
                    raise CustomValidationError(f"Invalid status transition from {current_status} to {new_status}")

    async def _validate_center_rules(
        self,
        document: Dict[str, Any],
        operation: str
    ) -> None:
        """Validate ATS center specific rules."""
        if operation == "create":
            required_equipment = ["speedTest", "brakeTest", "noiseTest"]
            if "equipment" in document:
                missing_equipment = [
                    eq for eq in required_equipment
                    if eq not in document["equipment"]
                ]
                if missing_equipment:
                    raise CustomValidationError(f"Missing required equipment: {', '.join(missing_equipment)}")

        elif operation == "update":
            if "status" in document:
                valid_statuses = ["active", "inactive", "suspended"]
                if document["status"] not in valid_statuses:
                    raise CustomValidationError(f"Invalid center status: {document['status']}")

    async def _validate_registration_number(self, registration_number: str) -> bool:
        """Validate vehicle registration number format."""
        pattern = r"^[A-Z]{2}\d{2}[A-Z]{1,2}\d{4}$"
        return bool(re.match(pattern, registration_number))

    async def _validate_manufacturing_year(self, year: int) -> bool:
        """Validate manufacturing year."""
        current_year = datetime.utcnow().year
        return 1900 <= year <= current_year

    async def _validate_email(self, email: str) -> bool:
        """Validate email format."""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))

    async def _validate_phone(self, phone: str) -> bool:
        """Validate phone number format."""
        pattern = r'^\+?[1-9]\d{9,14}$'
        return bool(re.match(pattern, phone))

    async def _validate_coordinates(self, coordinates: Dict[str, float]) -> bool:
        """Validate geographical coordinates."""
        try:
            lat = coordinates.get('latitude')
            lon = coordinates.get('longitude')

            return (
                isinstance(lat, (int, float)) and
                isinstance(lon, (int, float)) and
                -90 <= lat <= 90 and
                -180 <= lon <= 180
            )
        except Exception:
            return False


# Initialize database validator
db_validator = DatabaseValidator()