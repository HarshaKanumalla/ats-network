from typing import Dict, Any, List, Optional, Type, Callable
from datetime import datetime
import re
from bson import ObjectId
import logging
from pydantic import BaseModel, ValidationError

from ...core.exceptions import ValidationError, SchemaError
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
        # Define validation schemas for collections
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
            }
        }
        
        # Define field type validations
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
        operation: str = "create"
    ) -> None:
        """Validate document against schema and rules.
        
        Args:
            collection: Collection name
            document: Document to validate
            operation: Operation type (create/update)
            
        Raises:
            ValidationError: If validation fails
        """
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
                    raise ValidationError(f"Missing required fields: {', '.join(missing_fields)}")

            # Apply Pydantic model validation
            model_class = schema.get(operation)
            if model_class:
                try:
                    model_class(**document)
                except ValidationError as e:
                    raise ValidationError(f"Model validation failed: {str(e)}")

            # Apply field validators
            for field, validator in schema.get("validators", {}).items():
                if field in document:
                    if not await validator(document[field]):
                        raise ValidationError(f"Validation failed for field: {field}")

            # Check field types
            await self._validate_field_types(document)

            # Validate custom business rules
            await self._validate_business_rules(collection, document, operation)

        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"Document validation error: {str(e)}")
            raise ValidationError(f"Document validation failed: {str(e)}")

    async def validate_update(
        self,
        collection: str,
        update_query: Dict[str, Any],
        update_data: Dict[str, Any]
    ) -> None:
        """Validate update operation parameters.
        
        Args:
            collection: Collection name
            update_query: Update query criteria
            update_data: Update data
            
        Raises:
            ValidationError: If validation fails
        """
        try:
            schema = self.validation_schemas.get(collection)
            if not schema:
                return

            # Validate update operators
            for operator, value in update_data.items():
                if not operator.startswith('$'):
                    raise ValidationError("Invalid update operator format")
                
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

            # Validate business rules for update
            await self._validate_update_rules(
                collection,
                update_query,
                update_data
            )

        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"Update validation error: {str(e)}")
            raise ValidationError("Update validation failed")

    async def validate_reference(
        self,
        collection: str,
        field: str,
        value: Any,
        db = None
    ) -> bool:
        """Validate reference to another collection.
        
        Args:
            collection: Referenced collection
            field: Field name
            value: Field value
            db: Optional database instance
            
        Returns:
            True if reference is valid
        """
        try:
            # Convert string to ObjectId if needed
            if isinstance(value, str):
                value = ObjectId(value)

            # Check if referenced document exists
            result = await db[collection].find_one(
                {"_id": value},
                projection={"_id": 1}
            )
            return result is not None

        except Exception as e:
            logger.error(f"Reference validation error: {str(e)}")
            return False

    async def _validate_field_types(self, document: Dict[str, Any]) -> None:
        """Validate field data types.
        
        Args:
            document: Document to validate
            
        Raises:
            ValidationError: If type validation fails
        """
        for field, value in document.items():
            if value is not None:
                expected_type = self.type_validators.get(type(value).__name__)
                if expected_type and not isinstance(value, expected_type):
                    raise ValidationError(
                        f"Invalid type for field {field}. "
                        f"Expected {expected_type.__name__}, got {type(value).__name__}"
                    )

    async def _validate_business_rules(
        self,
        collection: str,
        document: Dict[str, Any],
        operation: str
    ) -> None:
        """Validate business-specific rules.
        
        Args:
            collection: Collection name
            document: Document to validate
            operation: Operation type
            
        Raises:
            ValidationError: If rule validation fails
        """
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
        """Validate test session specific rules.
        
        Args:
            document: Test session document
            operation: Operation type
            
        Raises:
            ValidationError: If validation fails
        """
        if operation == "create":
            # Validate test scheduling
            if "scheduledTime" in document:
                scheduled_time = document["scheduledTime"]
                if scheduled_time < datetime.utcnow():
                    raise ValidationError("Test cannot be scheduled in the past")

        elif operation == "update":
            # Validate status transitions
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
                    raise ValidationError(f"Invalid status transition from {current_status} to {new_status}")

    async def _validate_center_rules(
        self,
        document: Dict[str, Any],
        operation: str
    ) -> None:
        """Validate ATS center specific rules.
        
        Args:
            document: Center document
            operation: Operation type
            
        Raises:
            ValidationError: If validation fails
        """
        if operation == "create":
            # Validate equipment requirements
            required_equipment = ["speedTest", "brakeTest", "noiseTest"]
            if "equipment" in document:
                missing_equipment = [
                    eq for eq in required_equipment
                    if eq not in document["equipment"]
                ]
                if missing_equipment:
                    raise ValidationError(f"Missing required equipment: {', '.join(missing_equipment)}")

        elif operation == "update":
            # Validate status changes
            if "status" in document:
                valid_statuses = ["active", "inactive", "suspended"]
                if document["status"] not in valid_statuses:
                    raise ValidationError(f"Invalid center status: {document['status']}")

    async def _validate_array_operation(
        self,
        collection: str,
        value: Dict[str, Any]
    ) -> None:
        """Validate array update operations.
        
        Args:
            collection: Collection name
            value: Array operation value
            
        Raises:
            ValidationError: If validation fails
        """
        for field, items in value.items():
            if not isinstance(items, list):
                items = [items]
            
            for item in items:
                if isinstance(item, dict):
                    await self.validate_document(
                        collection,
                        item,
                        operation="update"
                    )

    # Field-specific validators
    async def _validate_email(self, email: str) -> bool:
        """Validate email format.
        
        Args:
            email: Email to validate
            
        Returns:
            True if email is valid
        """
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))

    async def _validate_phone(self, phone: str) -> bool:
        """Validate phone number format.
        
        Args:
            phone: Phone number to validate
            
        Returns:
            True if phone number is valid
        """
        pattern = r'^\+?[1-9]\d{9,14}$'
        return bool(re.match(pattern, phone))

    async def _validate_coordinates(
        self,
        coordinates: Dict[str, float]
    ) -> bool:
        """Validate geographical coordinates.
        
        Args:
            coordinates: Coordinates to validate
            
        Returns:
            True if coordinates are valid
        """
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