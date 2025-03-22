# backend/app/services/validation/document_service.py

from typing import Dict, Any, List, Optional, Tuple
import logging
from datetime import datetime, timedelta
import aiofiles
import hashlib
import magic
import cv2
import numpy as np
from PIL import Image
import pytesseract
from bson import ObjectId

from ...core.exceptions import ValidationError
from ...database import get_database
from ...config import get_settings
from ...services.notification import notification_service

logger = logging.getLogger(__name__)
settings = get_settings()

class DocumentValidationService:
    """Service for comprehensive document validation and verification."""
    
    def __init__(self):
        """Initialize document validation service with verification rules."""
        self.db = None
        
        # Document type configurations
        self.document_types = {
            'registration_certificate': {
                'required': True,
                'format': ['pdf', 'jpg', 'jpeg', 'png'],
                'max_size': 5 * 1024 * 1024,  # 5MB
                'expiry_check': True,
                'ocr_validation': True,
                'required_fields': [
                    'registration_number',
                    'owner_name',
                    'vehicle_class'
                ]
            },
            'insurance_policy': {
                'required': True,
                'format': ['pdf'],
                'max_size': 10 * 1024 * 1024,  # 10MB
                'expiry_check': True,
                'ocr_validation': True,
                'required_fields': [
                    'policy_number',
                    'validity_period',
                    'insured_value'
                ]
            },
            'fitness_certificate': {
                'required': False,
                'format': ['pdf', 'jpg', 'jpeg', 'png'],
                'max_size': 5 * 1024 * 1024,
                'expiry_check': True,
                'ocr_validation': True,
                'required_fields': [
                    'certificate_number',
                    'issue_date',
                    'validity'
                ]
            }
        }
        
        # OCR configuration
        self.ocr_config = {
            'lang': 'eng',
            'config': '--oem 3 --psm 6'
        }
        
        logger.info("Document validation service initialized")

    async def validate_document(
        self,
        document_type: str,
        file_path: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Perform comprehensive document validation."""
        try:
            validation_results = {
                'valid': True,
                'errors': [],
                'warnings': [],
                'metadata': {},
                'extracted_data': {}
            }
            
            # Check document type configuration
            config = self.document_types.get(document_type)
            if not config:
                raise ValidationError(f"Invalid document type: {document_type}")
            
            # Validate file format and size
            format_valid, format_error = await self._validate_file_format(
                file_path,
                config['format']
            )
            if not format_valid:
                validation_results['valid'] = False
                validation_results['errors'].append(format_error)
                return validation_results
            
            # Extract text using OCR if required
            if config['ocr_validation']:
                extracted_text = await self._extract_text(file_path)
                validation_results['extracted_data'] = await self._parse_document_data(
                    document_type,
                    extracted_text
                )
                
                # Validate required fields
                missing_fields = self._validate_required_fields(
                    config['required_fields'],
                    validation_results['extracted_data']
                )
                if missing_fields:
                    validation_results['valid'] = False
                    validation_results['errors'].append(
                        f"Missing required fields: {', '.join(missing_fields)}"
                    )
            
            # Check document expiry if required
            if config['expiry_check'] and validation_results['extracted_data'].get('expiry_date'):
                expiry_valid, expiry_warning = self._check_expiry(
                    validation_results['extracted_data']['expiry_date']
                )
                if not expiry_valid:
                    validation_results['valid'] = False
                    validation_results['errors'].append("Document has expired")
                elif expiry_warning:
                    validation_results['warnings'].append(expiry_warning)
            
            # Additional metadata validation
            if metadata:
                metadata_valid, metadata_errors = self._validate_metadata(metadata)
                if not metadata_valid:
                    validation_results['valid'] = False
                    validation_results['errors'].extend(metadata_errors)
            
            # Generate document hash
            validation_results['metadata']['document_hash'] = await self._generate_document_hash(
                file_path
            )
            
            # Store validation results
            await self._store_validation_results(
                document_type,
                validation_results
            )
            
            return validation_results
            
        except Exception as e:
            logger.error(f"Document validation error: {str(e)}")
            raise ValidationError(f"Failed to validate document: {str(e)}")

    async def _extract_text(self, file_path: str) -> str:
        """Extract text from document using OCR."""
        try:
            # Handle different file types
            file_extension = file_path.split('.')[-1].lower()
            
            if file_extension in ['jpg', 'jpeg', 'png']:
                # Process image
                img = cv2.imread(file_path)
                img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                
                # Image preprocessing for better OCR
                img = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
                img = cv2.medianBlur(img, 3)
                
                # Perform OCR
                text = pytesseract.image_to_string(
                    img,
                    lang=self.ocr_config['lang'],
                    config=self.ocr_config['config']
                )
                
            elif file_extension == 'pdf':
                # Convert PDF pages to images and extract text
                text = ""
                # Implementation for PDF text extraction
                pass
            
            else:
                raise ValidationError(f"Unsupported file type: {file_extension}")
            
            return text.strip()
            
        except Exception as e:
            logger.error(f"Text extraction error: {str(e)}")
            raise ValidationError("Failed to extract text from document")

    async def _parse_document_data(
        self,
        document_type: str,
        text: str
    ) -> Dict[str, Any]:
        """Parse extracted text to get required fields."""
        try:
            data = {}
            
            if document_type == 'registration_certificate':
                # Extract registration details
                reg_number = self._extract_registration_number(text)
                owner_name = self._extract_owner_name(text)
                vehicle_class = self._extract_vehicle_class(text)
                
                data.update({
                    'registration_number': reg_number,
                    'owner_name': owner_name,
                    'vehicle_class': vehicle_class
                })
                
            elif document_type == 'insurance_policy':
                # Extract insurance details
                policy_number = self._extract_policy_number(text)
                validity = self._extract_validity_period(text)
                insured_value = self._extract_insured_value(text)
                
                data.update({
                    'policy_number': policy_number,
                    'validity_period': validity,
                    'insured_value': insured_value
                })
                
            # Add parsing for other document types
            
            return data
            
        except Exception as e:
            logger.error(f"Document parsing error: {str(e)}")
            raise ValidationError("Failed to parse document data")

    def _validate_required_fields(
        self,
        required_fields: List[str],
        extracted_data: Dict[str, Any]
    ) -> List[str]:
        """Validate presence of required fields in extracted data."""
        missing_fields = []
        
        for field in required_fields:
            if not extracted_data.get(field):
                missing_fields.append(field)
                
        return missing_fields

    def _check_expiry(
        self,
        expiry_date: datetime
    ) -> Tuple[bool, Optional[str]]:
        """Check document expiry status."""
        current_date = datetime.utcnow()
        
        if expiry_date < current_date:
            return False, "Document has expired"
            
        # Warning for documents expiring soon
        if expiry_date - current_date <= timedelta(days=30):
            return True, "Document will expire within 30 days"
            
        return True, None

    async def _generate_document_hash(self, file_path: str) -> str:
        """Generate unique hash for document content."""
        try:
            async with aiofiles.open(file_path, 'rb') as file:
                content = await file.read()
                return hashlib.sha256(content).hexdigest()
                
        except Exception as e:
            logger.error(f"Hash generation error: {str(e)}")
            raise ValidationError("Failed to generate document hash")

    async def _store_validation_results(
        self,
        document_type: str,
        results: Dict[str, Any]
    ) -> None:
        """Store document validation results."""
        try:
            db = await get_database()
            
            validation_record = {
                'document_type': document_type,
                'validation_results': results,
                'validated_at': datetime.utcnow()
            }
            
            await db.document_validations.insert_one(validation_record)
            
            # Send notifications for validation issues
            if not results['valid']:
                await notification_service.send_document_validation_notification(
                    document_type=document_type,
                    errors=results['errors']
                )
                
        except Exception as e:
            logger.error(f"Validation storage error: {str(e)}")

# Initialize document validation service
document_validation_service = DocumentValidationService()