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
import fitz  # PyMuPDF
import re
from bson import ObjectId
from dateutil import parser

from ...core.exceptions import ValidationError
from ...database import get_database
from ...config import get_settings
from ...services.notification import notification_service

logger = logging.getLogger(__name__)
settings = get_settings()

class DocumentValidationService:
    """Service for comprehensive document validation and verification."""
    
    def __init__(self):
        # ...existing initialization code...

    async def _extract_text(self, file_path: str) -> str:
        """Extract text from document using OCR."""
        try:
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
                text = await self._extract_text_from_pdf(file_path)
            else:
                raise ValidationError(f"Unsupported file type: {file_extension}")
            
            return text.strip()
            
        except Exception as e:
            logger.error(f"Text extraction error: {str(e)}")
            raise ValidationError("Failed to extract text from document")

    async def _extract_text_from_pdf(self, file_path: str) -> str:
        """Extract text from PDF document including text in images."""
        try:
            text = ""
            doc = fitz.open(file_path)
            
            for page_num in range(doc.page_count):
                page = doc[page_num]
                
                # Extract text from page
                text += page.get_text()
                
                # Process images in the page
                image_list = page.get_images()
                for img_info in image_list:
                    xref = img_info[0]
                    base_image = doc.extract_image(xref)
                    image_data = base_image["image"]
                    
                    # Convert image to OpenCV format
                    nparr = np.frombuffer(image_data, np.uint8)
                    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    
                    # Process image for OCR
                    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                    processed = cv2.threshold(
                        gray, 0, 255,
                        cv2.THRESH_BINARY + cv2.THRESH_OTSU
                    )[1]
                    
                    # Perform OCR on image
                    img_text = pytesseract.image_to_string(
                        processed,
                        lang=self.ocr_config['lang'],
                        config=self.ocr_config['config']
                    )
                    text += f"\n{img_text}"
            
            return text.strip()
            
        except Exception as e:
            logger.error(f"PDF text extraction error: {str(e)}")
            raise ValidationError("Failed to extract text from PDF")

    def _extract_registration_number(self, text: str) -> Optional[str]:
        """Extract vehicle registration number from text."""
        patterns = [
            r'[A-Z]{2}\s*\d{2}\s*[A-Z]{1,2}\s*\d{4}',  # Format: MH 12 AB 1234
            r'[A-Z]{2}\d{2}[A-Z]{1,2}\d{4}'            # Format: MH12AB1234
        ]
        
        try:
            for pattern in patterns:
                match = re.search(pattern, text)
                if match:
                    return match.group().replace(' ', '')
            return None
            
        except Exception as e:
            logger.error(f"Registration number extraction error: {str(e)}")
            return None

    def _extract_owner_name(self, text: str) -> Optional[str]:
        """Extract vehicle owner name from text."""
        try:
            indicators = [
                "OWNER'S NAME",
                "NAME OF OWNER",
                "REGISTERED OWNER"
            ]
            
            lines = text.split('\n')
            for i, line in enumerate(lines):
                for indicator in indicators:
                    if indicator in line.upper():
                        # Check next line for name
                        if i + 1 < len(lines):
                            name = lines[i + 1].strip()
                            if name and len(name.split()) >= 2:
                                return name
            return None
            
        except Exception as e:
            logger.error(f"Owner name extraction error: {str(e)}")
            return None

    def _extract_vehicle_class(self, text: str) -> Optional[str]:
        """Extract vehicle class from text."""
        try:
            vehicle_classes = [
                "LMV", "MCWG", "HMV", "HPMV", "HGMV",
                "LIGHT MOTOR VEHICLE", "HEAVY MOTOR VEHICLE",
                "TWO WHEELER", "MOTOR CYCLE", "SCOOTER"
            ]
            
            text_upper = text.upper()
            for vc in vehicle_classes:
                if vc in text_upper:
                    return vc
            return None
            
        except Exception as e:
            logger.error(f"Vehicle class extraction error: {str(e)}")
            return None

    def _extract_policy_number(self, text: str) -> Optional[str]:
        """Extract insurance policy number from text."""
        try:
            patterns = [
                r'POLICY\s*(?:NO|NUMBER|#)[\s.:]*([A-Z0-9-/]+)',
                r'(?:POL|POLICY)[\s.:]*([A-Z0-9-/]+)'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, text.upper())
                if match:
                    return match.group(1).strip()
            return None
            
        except Exception as e:
            logger.error(f"Policy number extraction error: {str(e)}")
            return None

    def _extract_validity_period(self, text: str) -> Optional[Dict[str, datetime]]:
        """Extract policy validity period from text."""
        try:
            date_patterns = [
                r'VALID\s*(?:FROM|FROM DATE)[\s.:]*(\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})',
                r'(?:VALID|EXPIRY)\s*(?:TILL|UNTIL|UPTO)[\s.:]*(\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})'
            ]
            
            validity = {}
            for pattern in date_patterns:
                match = re.search(pattern, text.upper())
                if match:
                    try:
                        date_str = match.group(1)
                        date = parser.parse(date_str)
                        if 'FROM' in pattern:
                            validity['start_date'] = date
                        else:
                            validity['end_date'] = date
                    except:
                        continue
                        
            return validity if validity else None
            
        except Exception as e:
            logger.error(f"Validity period extraction error: {str(e)}")
            return None

    def _extract_insured_value(self, text: str) -> Optional[float]:
        """Extract insured value from text."""
        try:
            patterns = [
                r'(?:INSURED|IDV|DECLARED)\s*VALUE[\s.:]*(?:RS\.?|INR)?\s*([\d,]+)',
                r'IDV[\s.:]*(?:RS\.?|INR)?\s*([\d,]+)'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, text.upper())
                if match:
                    value_str = match.group(1).replace(',', '')
                    return float(value_str)
            return None
            
        except Exception as e:
            logger.error(f"Insured value extraction error: {str(e)}")
            return None

    async def _validate_file_format(
        self,
        file_path: str,
        allowed_formats: List[str]
    ) -> Tuple[bool, Optional[str]]:
        """Validate file format and size."""
        try:
            # Check file size
            async with aiofiles.open(file_path, 'rb') as file:
                content = await file.read()
                file_size = len(content)
            
            # Get MIME type
            mime = magic.Magic(mime=True)
            file_type = mime.from_buffer(content)
            
            # Convert MIME type to extension
            mime_to_ext = {
                'application/pdf': 'pdf',
                'image/jpeg': 'jpg',
                'image/png': 'png'
            }
            
            detected_format = mime_to_ext.get(file_type)
            if not detected_format or detected_format not in allowed_formats:
                return False, f"Invalid file format. Allowed formats: {', '.join(allowed_formats)}"
            
            # Check file size
            max_size = self.document_types.get(detected_format, {}).get('max_size', 5 * 1024 * 1024)
            if file_size > max_size:
                return False, f"File size exceeds maximum allowed ({max_size/1024/1024}MB)"
            
            return True, None
            
        except Exception as e:
            logger.error(f"File format validation error: {str(e)}")
            return False, "Failed to validate file format"

    async def _validate_metadata(
        self,
        metadata: Dict[str, Any]
    ) -> Tuple[bool, List[str]]:
        """Validate document metadata."""
        errors = []
        
        try:
            # Required metadata fields
            required_fields = {
                'document_id': str,
                'issuing_authority': str,
                'issue_date': datetime
            }
            
            # Check required fields
            for field, field_type in required_fields.items():
                if field not in metadata:
                    errors.append(f"Missing required metadata field: {field}")
                    continue
                    
                if not isinstance(metadata[field], field_type):
                    errors.append(f"Invalid type for {field}: expected {field_type.__name__}")
            
            # Validate issue date
            if 'issue_date' in metadata and isinstance(metadata['issue_date'], datetime):
                if metadata['issue_date'] > datetime.utcnow():
                    errors.append("Issue date cannot be in the future")
            
            # Validate issuing authority
            if 'issuing_authority' in metadata:
                valid_authorities = await self._get_valid_authorities()
                if metadata['issuing_authority'] not in valid_authorities:
                    errors.append("Invalid issuing authority")
            
            return not bool(errors), errors
            
        except Exception as e:
            logger.error(f"Metadata validation error: {str(e)}")
            return False, ["Failed to validate metadata"]

    async def _get_valid_authorities(self) -> List[str]:
        """Get list of valid issuing authorities."""
        try:
            db = await get_database()
            authorities = await db.issuing_authorities.find(
                {"status": "active"}
            ).distinct("name")
            return authorities
            
        except Exception as e:
            logger.error(f"Authority lookup error: {str(e)}")
            return []

# Initialize document validation service
document_validation_service = DocumentValidationService()