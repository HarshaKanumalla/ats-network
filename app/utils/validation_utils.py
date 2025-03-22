# backend/app/utils/validation_utils.py

import re
from typing import Optional, Dict, Any, List
from datetime import datetime
import logging
from email_validator import validate_email, EmailNotValidError

logger = logging.getLogger(__name__)

class ValidationUtils:
    """Utility functions for data validation."""

    # Regular expression patterns
    PATTERNS = {
        'phone': r'^\+?[1-9]\d{9,14}$',
        'pin_code': r'^\d{6}$',
        'vehicle_number': r'^[A-Z]{2}[0-9]{2}[A-Z]{1,2}[0-9]{4}$',
        'ats_code': r'^ATS\d{6}$',
        'pan_card': r'^[A-Z]{5}[0-9]{4}[A-Z]$',
        'gst_number': r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[0-9A-Z]{1}[Z]{1}[0-9A-Z]{1}$'
    }

    # Document validation constants
    ALLOWED_FILE_TYPES = {
        'image': ['image/jpeg', 'image/png'],
        'document': ['application/pdf', 'application/msword', 
                    'application/vnd.openxmlformats-officedocument.wordprocessingml.document']
    }
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

    @staticmethod
    def validate_phone_number(phone: str) -> bool:
        """
        Validate phone number format.
        
        Args:
            phone: Phone number to validate
            
        Returns:
            bool: True if valid, False otherwise
        """
        if not phone:
            return False
        return bool(re.match(ValidationUtils.PATTERNS['phone'], phone))

    @staticmethod
    def validate_pin_code(pin_code: str) -> bool:
        """
        Validate Indian PIN code format.
        
        Args:
            pin_code: PIN code to validate
            
        Returns:
            bool: True if valid, False otherwise
        """
        if not pin_code:
            return False
        return bool(re.match(ValidationUtils.PATTERNS['pin_code'], pin_code))

    @staticmethod
    def validate_vehicle_number(number: str) -> bool:
        """
        Validate Indian vehicle registration number format.
        
        Args:
            number: Vehicle number to validate
            
        Returns:
            bool: True if valid, False otherwise
        """
        if not number:
            return False
        return bool(re.match(ValidationUtils.PATTERNS['vehicle_number'], number))

    @staticmethod
    def validate_email_address(email: str) -> bool:
        """
        Validate email address format and domain.
        
        Args:
            email: Email address to validate
            
        Returns:
            bool: True if valid, False otherwise
        """
        try:
            validate_email(email)
            return True
        except EmailNotValidError:
            return False

    @staticmethod
    def validate_document(file_data: Dict[str, Any], file_type: str) -> Dict[str, Any]:
        """
        Validate uploaded document properties.
        
        Args:
            file_data: Dictionary containing file information
            file_type: Expected type of file
            
        Returns:
            Dict[str, Any]: Validation results with status and errors
        """
        result = {"valid": True, "errors": []}

        # Check file size
        if file_data.get('size', 0) > ValidationUtils.MAX_FILE_SIZE:
            result["valid"] = False
            result["errors"].append("File size exceeds maximum limit")

        # Check file type
        content_type = file_data.get('content_type', '')
        if file_type in ValidationUtils.ALLOWED_FILE_TYPES:
            if content_type not in ValidationUtils.ALLOWED_FILE_TYPES[file_type]:
                result["valid"] = False
                result["errors"].append(f"Invalid file type for {file_type}")

        return result

    @staticmethod
    def validate_ats_center_code(code: str) -> bool:
        """
        Validate ATS center code format.
        
        Args:
            code: Center code to validate
            
        Returns:
            bool: True if valid, False otherwise
        """
        if not code:
            return False
        return bool(re.match(ValidationUtils.PATTERNS['ats_code'], code))

    @staticmethod
    def validate_date_range(start_date: datetime, end_date: datetime) -> bool:
        """
        Validate date range logic.
        
        Args:
            start_date: Start date of range
            end_date: End date of range
            
        Returns:
            bool: True if valid, False otherwise
        """
        if not start_date or not end_date:
            return False
        return start_date < end_date

    @staticmethod
    def validate_coordinates(latitude: float, longitude: float) -> bool:
        """
        Validate geographical coordinates.
        
        Args:
            latitude: Latitude value
            longitude: Longitude value
            
        Returns:
            bool: True if valid, False otherwise
        """
        try:
            return -90 <= float(latitude) <= 90 and -180 <= float(longitude) <= 180
        except (TypeError, ValueError):
            return False

    @staticmethod
    def validate_pan_card(pan_number: str) -> bool:
        """
        Validate Indian PAN card number format.
        
        Args:
            pan_number: PAN number to validate
            
        Returns:
            bool: True if valid, False otherwise
        """
        if not pan_number:
            return False
        return bool(re.match(ValidationUtils.PATTERNS['pan_card'], pan_number))

    @staticmethod
    def validate_gst_number(gst_number: str) -> bool:
        """
        Validate Indian GST number format.
        
        Args:
            gst_number: GST number to validate
            
        Returns:
            bool: True if valid, False otherwise
        """
        if not gst_number:
            return False
        return bool(re.match(ValidationUtils.PATTERNS['gst_number'], gst_number))

    @staticmethod
    def validate_test_data(test_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate vehicle test measurement data.
        
        Args:
            test_type: Type of test being performed
            data: Test measurement data
            
        Returns:
            Dict[str, Any]: Validation results with status and errors
        """
        result = {"valid": True, "errors": []}
        
        # Test-specific validation rules
        validation_rules = {
            'speed_test': {
                'speed': lambda x: 0 <= x <= 200,
                'duration': lambda x: x > 0
            },
            'brake_test': {
                'force': lambda x: 0 <= x <= 1000,
                'efficiency': lambda x: 0 <= x <= 100
            },
            'noise_test': {
                'decibels': lambda x: 0 <= x <= 120
            }
        }

        if test_type in validation_rules:
            for field, validator in validation_rules[test_type].items():
                if field not in data:
                    result["valid"] = False
                    result["errors"].append(f"Missing required field: {field}")
                elif not validator(data[field]):
                    result["valid"] = False
                    result["errors"].append(f"Invalid value for {field}")

        return result

    @staticmethod
    def sanitize_input(input_data: str) -> str:
        """
        Sanitize user input to prevent injection attacks.
        
        Args:
            input_data: String to sanitize
            
        Returns:
            str: Sanitized string
        """
        if not input_data:
            return ""
        
        # Remove potentially dangerous characters
        sanitized = re.sub(r'[<>"\';()]', '', input_data)
        # Remove multiple spaces
        sanitized = ' '.join(sanitized.split())
        return sanitized.strip()

    @staticmethod
    def validate_address(address: Dict[str, str]) -> Dict[str, bool]:
        """
        Validate address components.
        
        Args:
            address: Dictionary containing address components
            
        Returns:
            Dict[str, bool]: Validation results for each component
        """
        results = {}
        
        # Required fields
        required_fields = ['street', 'city', 'state', 'pin_code']
        
        for field in required_fields:
            # Check presence and minimum length
            results[field] = bool(
                address.get(field) and 
                len(address[field].strip()) >= 2
            )
        
        # Additional PIN code validation
        if results.get('pin_code'):
            results['pin_code'] = ValidationUtils.validate_pin_code(
                address['pin_code']
            )
            
        return results