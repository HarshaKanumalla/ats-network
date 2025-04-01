"""
Service for comprehensive data validation, cleaning, and integrity checking.
Ensures data quality and consistency across the system.
"""

from typing import Dict, Any, List, Optional, Union, Callable
import logging
import re
from datetime import datetime, timedelta
from decimal import Decimal

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
        self.phone_patterns = {
            'IN': r'^\+91[6-9]\d{9}$',  # Indian format
            'US': r'^\+1[2-9]\d{9}$',   # US format
            'UK': r'^\+44[1-9]\d{9}$'   # UK format
        }
        self.address_rules = {
            'min_length': 10,
            'max_length': 200,
            'allowed_chars': r'^[a-zA-Z0-9\s,.-/#]+$'
        }
        logger.info("Validation service initialized")

    def _initialize_validation_rules(self) -> Dict[str, Dict[str, Any]]:
        """Initialize data validation rules."""
        return {
            "speed_test": {
                "speed": {
                    "validator": lambda x: isinstance(x, (int, float)) and 0 <= x <= 200,
                    "message": "Speed must be between 0 and 200 km/h",
                    "required": True
                },
                "timestamp": {
                    "validator": self._is_valid_timestamp,
                    "message": "Invalid timestamp",
                    "required": True
                },
                "duration": {
                    "validator": lambda x: isinstance(x, (int, float)) and 0 <= x <= 300,
                    "message": "Duration must be between 0 and 300 seconds",
                    "required": True
                }
            },
            "brake_test": {
                "force": {
                    "validator": lambda x: isinstance(x, (int, float)) and 0 <= x <= 1000,
                    "message": "Brake force must be between 0 and 1000 N",
                    "required": True
                },
                "response_time": {
                    "validator": lambda x: isinstance(x, (int, float)) and 0 <= x <= 5,
                    "message": "Response time must be between 0 and 5 seconds",
                    "required": True
                },
                "pedal_travel": {
                    "validator": lambda x: isinstance(x, (int, float)) and 0 <= x <= 200,
                    "message": "Pedal travel must be between 0 and 200 mm",
                    "required": True
                }
            },
            "noise_test": {
                "noise_level": {
                    "validator": lambda x: isinstance(x, (int, float)) and 0 <= x <= 120,
                    "message": "Noise level must be between 0 and 120 dB",
                    "required": True
                },
                "ambient_noise": {
                    "validator": lambda x: isinstance(x, (int, float)) and 0 <= x <= 100,
                    "message": "Ambient noise must be between 0 and 100 dB",
                    "required": True
                },
                "frequency": {
                    "validator": lambda x: isinstance(x, (int, float)) and 20 <= x <= 20000,
                    "message": "Frequency must be between 20 and 20000 Hz",
                    "required": True
                }
            },
            "headlight_test": {
                "intensity": {
                    "validator": lambda x: isinstance(x, (int, float)) and 0 <= x <= 1000,
                    "message": "Light intensity must be between 0 and 1000 lux",
                    "required": True
                },
                "alignment": {
                    "validator": lambda x: isinstance(x, (int, float)) and -5 <= x <= 5,
                    "message": "Alignment must be between -5 and 5 degrees",
                    "required": True
                },
                "glare": {
                    "validator": lambda x: isinstance(x, (int, float)) and 0 <= x <= 100,
                    "message": "Glare must be between 0 and 100 units",
                    "required": True
                }
            }
        }

    async def validate_registration_data(
        self,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate and clean registration data."""
        try:
            # Apply standard cleaning
            cleaned_data = self._clean_input_data(data)
            
            # Validate required fields
            required_fields = [
                "email", "full_name", "phone_number",
                "ats_address", "city", "district", "state", "pin_code"
            ]
            self._validate_required_fields(cleaned_data, required_fields)
            
            # Validate email format
            if not self._is_valid_email(cleaned_data["email"]):
                raise ValidationError("Invalid email format")
            
            # Validate phone number
            if not self._is_valid_phone(cleaned_data["phone_number"]):
                raise ValidationError("Invalid phone number format")
            
            # Validate PIN code
            if not self._is_valid_pin_code(cleaned_data["pin_code"]):
                raise ValidationError("Invalid PIN code format")
            
            # Validate address
            if not self._is_valid_address(cleaned_data["ats_address"]):
                raise ValidationError("Invalid address format")
            
            # Normalize data
            cleaned_data = self._normalize_data(cleaned_data)
            
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
            
            # Clean input data
            cleaned_data = self._clean_input_data(data)
            
            # Apply validation rules
            validated_data = {}
            for field, rule in validation_rule.items():
                if field in cleaned_data:
                    value = cleaned_data[field]
                    if not rule["validator"](value):
                        raise ValidationError(
                            f"Invalid value for {field}: {rule['message']}"
                        )
                    validated_data[field] = value
                elif rule.get("required", False):
                    raise ValidationError(f"Missing required field: {field}")
            
            # Normalize numeric values
            validated_data = self._normalize_numeric_values(validated_data)
            
            return validated_data
            
        except Exception as e:
            logger.error(f"Test data validation error: {str(e)}")
            raise ValidationError(f"Validation failed for {test_type}: {str(e)}")

    def _clean_input_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Clean and sanitize input data."""
        cleaned = {}
        for key, value in data.items():
            if isinstance(value, str):
                # Strip whitespace and remove special characters
                cleaned[key] = re.sub(r'[^\w\s@.,-/#]', '', value.strip())
            elif isinstance(value, (int, float)):
                # Normalize numeric values
                cleaned[key] = self._normalize_numeric(value)
            else:
                cleaned[key] = value
        return cleaned

    def _normalize_numeric(self, value: Union[int, float]) -> Decimal:
        """Normalize numeric values to decimal with fixed precision."""
        try:
            return Decimal(str(value)).quantize(Decimal('0.001'))
        except:
            return Decimal(str(value))

    def _normalize_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize all data types in the dictionary."""
        normalized = {}
        for key, value in data.items():
            if isinstance(value, (int, float)):
                normalized[key] = self._normalize_numeric(value)
            elif isinstance(value, str):
                normalized[key] = value.strip()
            else:
                normalized[key] = value
        return normalized

    def _normalize_numeric_values(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize numeric values in test data."""
        normalized = {}
        for key, value in data.items():
            if isinstance(value, (int, float)):
                normalized[key] = self._normalize_numeric(value)
            else:
                normalized[key] = value
        return normalized

    def _is_valid_email(self, email: str) -> bool:
        """Validate email format."""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))

    def _is_valid_phone(self, phone: str, country: str = 'IN') -> bool:
        """Validate phone number format."""
        pattern = self.phone_patterns.get(country)
        if not pattern:
            return True  # Skip validation for unknown country codes
        return bool(re.match(pattern, phone))

    def _is_valid_pin_code(self, pin_code: str) -> bool:
        """Validate PIN code format."""
        return bool(re.match(r'^\d{6}$', pin_code))

    def _is_valid_address(self, address: str) -> bool:
        """Validate address format."""
        if not (self.address_rules['min_length'] <= len(address) <= self.address_rules['max_length']):
            return False
        return bool(re.match(self.address_rules['allowed_chars'], address))

    def _is_valid_timestamp(self, timestamp: Union[str, datetime]) -> bool:
        """Validate timestamp."""
        try:
            if isinstance(timestamp, str):
                timestamp = datetime.fromisoformat(timestamp)
            
            # Check if timestamp is within reasonable range
            now = datetime.utcnow()
            min_time = now - timedelta(hours=1)
            max_time = now + timedelta(minutes=5)
            
            return min_time <= timestamp <= max_time
        except:
            return False

    def _validate_required_fields(
        self,
        data: Dict[str, Any],
        required: List[str]
    ) -> None:
        """Validate presence of required fields."""
        missing = [field for field in required if not data.get(field)]
        if missing:
            raise ValidationError(f"Missing required fields: {', '.join(missing)}")

# Initialize validation service
validation_service = ValidationService()