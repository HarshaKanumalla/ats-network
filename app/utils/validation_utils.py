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
    def validate_phone_number(phone: str) -> Dict[str, Any]:
        """
        Validate phone number format.
        
        Args:
            phone: Phone number to validate
            
        Returns:
            Dict[str, Any]: Validation result with status and error message
        """
        if not phone:
            return {"valid": False, "error": "Phone number is required"}
        if not re.match(ValidationUtils.PATTERNS['phone'], phone):
            return {"valid": False, "error": "Invalid phone number format"}
        return {"valid": True}

    @staticmethod
    def validate_email_address(email: str) -> Dict[str, Any]:
        """
        Validate email address format and domain.
        
        Args:
            email: Email address to validate
            
        Returns:
            Dict[str, Any]: Validation result with status and error message
        """
        try:
            validate_email(email)
            return {"valid": True}
        except EmailNotValidError as e:
            return {"valid": False, "error": str(e)}

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

        # Validate file name
        file_name = file_data.get('name', '')
        if not file_name or not re.match(r'^[\w,\s-]+\.[A-Za-z]{3,4}$', file_name):
            result["valid"] = False
            result["errors"].append("Invalid file name")

        return result

    @staticmethod
    def validate_address(address: Dict[str, str]) -> Dict[str, Any]:
        """
        Validate address components.
        
        Args:
            address: Dictionary containing address components
            
        Returns:
            Dict[str, Any]: Validation results for each component
        """
        results = {"valid": True, "errors": []}
        
        # Required fields
        required_fields = ['street', 'city', 'state', 'pin_code']
        
        for field in required_fields:
            if not address.get(field) or len(address[field].strip()) < 2:
                results["valid"] = False
                results["errors"].append(f"Invalid or missing {field}")
        
        # Additional PIN code validation
        if 'pin_code' in address and not ValidationUtils.validate_pin_code(address['pin_code']):
            results["valid"] = False
            results["errors"].append("Invalid PIN code")
            
        return results