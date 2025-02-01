# backend/app/services/validation/service.py

"""
Service for comprehensive data validation, cleaning, and integrity checking.
Ensures data quality and consistency across the system.
"""

from typing import Dict, Any, List, Optional
import logging
import re
from datetime import datetime

from ...core.exceptions import ValidationError
from ...database import get_database
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class ValidationService:
    """Service for data validation and cleaning operations."""
    
    def __init__(self):
        """Initialize validation service with validation rules."""
        self.db = None
        self.validation_rules = self._initialize_validation_rules()
        logger.info("Validation service initialized")

    async def validate_registration_data(
        self,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate and clean registration data."""
        try:
            # Apply standard cleaning
            cleaned_data = self._clean_input_data(data)
            
            # Validate required fields
            self._validate_required_fields(cleaned_data, [
                "email", "full_name", "ats_address", "city",
                "district", "state", "pin_code"
            ])
            
            # Validate email format
            if not self._is_valid_email(cleaned_data["email"]):
                raise ValidationError("Invalid email format")
            
            # Validate PIN code
            if not self._is_valid_pin_code(cleaned_data["pin_code"]):
                raise ValidationError("Invalid PIN code format")
            
            return cleaned_data
            
        except Exception as e:
            logger.error(f"Registration validation error: {str(e)}")
            raise ValidationError(str(e))

    async def validate_test_data(
        self,
        test_type: str,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate test measurement data."""
        try:
            validation_rule = self.validation_rules.get(test_type)
            if not validation_rule:
                raise ValidationError(f"Unknown test type: {test_type}")
            
            # Apply validation rules
            cleaned_data = {}
            for field, rule in validation_rule.items():
                if field in data:
                    value = data[field]
                    if not rule["validator"](value):
                        raise ValidationError(
                            f"Invalid value for {field}: {rule['message']}"
                        )
                    cleaned_data[field] = value
                elif rule.get("required", False):
                    raise ValidationError(f"Missing required field: {field}")
            
            return cleaned_data
            
        except Exception as e:
            logger.error(f"Test data validation error: {str(e)}")
            raise ValidationError(str(e))

    def _initialize_validation_rules(self) -> Dict[str, Dict[str, Any]]:
        """Initialize data validation rules."""
        return {
            "speed_test": {
                "speed": {
                    "validator": lambda x: isinstance(x, (int, float)) and 0 <= x <= 200,
                    "message": "Speed must be between 0 and 200 km/h",
                    "required": True
                }
            },
            "brake_test": {
                "force": {
                    "validator": lambda x: isinstance(x, (int, float)) and 0 <= x <= 1000,
                    "message": "Brake force must be between 0 and 1000 N",
                    "required": True
                }
            }
            # Add rules for other test types
        }

    def _clean_input_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Clean and sanitize input data."""
        cleaned = {}
        for key, value in data.items():
            if isinstance(value, str):
                # Strip whitespace and remove special characters
                cleaned[key] = re.sub(r'[^\w\s@.-]', '', value.strip())
            else:
                cleaned[key] = value
        return cleaned

    def _is_valid_email(self, email: str) -> bool:
        """Validate email format."""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))

    def _is_valid_pin_code(self, pin_code: str) -> bool:
        """Validate PIN code format."""
        return bool(re.match(r'^\d{6}$', pin_code))

# Initialize validation service
validation_service = ValidationService()