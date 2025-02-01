# backend/app/utils/validation_utils.py

import re
from typing import Optional

class ValidationUtils:
    """Utility functions for data validation."""
    
    @staticmethod
    def validate_phone_number(phone: str) -> bool:
        """Validate phone number format."""
        pattern = r'^\+?[1-9]\d{9,14}$'
        return bool(re.match(pattern, phone))

    @staticmethod
    def validate_pin_code(pin_code: str) -> bool:
        """Validate Indian PIN code format."""
        return bool(re.match(r'^\d{6}$', pin_code))

    @staticmethod
    def validate_vehicle_number(number: str) -> bool:
        """Validate Indian vehicle registration number format."""
        pattern = r'^[A-Z]{2}[0-9]{2}[A-Z]{1,2}[0-9]{4}$'
        return bool(re.match(pattern, number))