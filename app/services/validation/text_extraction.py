# backend/app/services/validation/text_extraction.py

import re
from typing import Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class TextExtractionHelper:
    """Helper class for extracting specific information from document text."""
    
    def __init__(self):
        """Initialize text extraction patterns."""
        # Registration number patterns
        self.reg_number_pattern = r'[A-Z]{2}\s*\d{2}\s*[A-Z]{1,2}\s*\d{4}'
        
        # Policy number patterns
        self.policy_patterns = {
            'general': r'Policy\s+No\.?\s*[:.]?\s*([A-Z0-9-/]+)',
            'specific': {
                'national': r'NIC-\d{10}',
                'oriental': r'OIC-\d{12}',
                'united': r'UI-\d{8}-\d{4}'
            }
        }
        
        # Date patterns
        self.date_patterns = [
            r'\d{2}[-/]\d{2}[-/]\d{4}',    # DD-MM-YYYY or DD/MM/YYYY
            r'\d{4}[-/]\d{2}[-/]\d{2}',    # YYYY-MM-DD or YYYY/MM/DD
            r'\d{2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}'  # DD Month YYYY
        ]
        
        # Amount patterns
        self.amount_pattern = r'(?:Rs\.|₹|INR)?\s*(\d+(?:,\d+)*(?:\.\d{2})?)'
        
        # Common Indian name patterns
        self.name_pattern = r'(?:Mr\.|Mrs\.|Ms\.|Dr\.)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)'
        
        logger.info("Text extraction helper initialized")

    def extract_registration_number(self, text: str) -> Optional[str]:
        """Extract vehicle registration number from text."""
        try:
            # Search for registration number pattern
            matches = re.findall(self.reg_number_pattern, text)
            
            if matches:
                # Clean up the matched registration number
                reg_number = matches[0]
                reg_number = re.sub(r'\s+', '', reg_number)  # Remove spaces
                return reg_number
                
            return None
            
        except Exception as e:
            logger.error(f"Registration number extraction error: {str(e)}")
            return None

    def extract_policy_number(self, text: str) -> Optional[str]:
        """Extract insurance policy number from text."""
        try:
            # Try specific company patterns first
            for company_pattern in self.policy_patterns['specific'].values():
                match = re.search(company_pattern, text)
                if match:
                    return match.group(0)
            
            # Try general pattern
            match = re.search(self.policy_patterns['general'], text)
            if match:
                return match.group(1)
                
            return None
            
        except Exception as e:
            logger.error(f"Policy number extraction error: {str(e)}")
            return None

    def extract_validity_period(self, text: str) -> Optional[Dict[str, datetime]]:
        """Extract document validity period."""
        try:
            dates = []
            
            # Try all date patterns
            for pattern in self.date_patterns:
                matches = re.finditer(pattern, text)
                for match in matches:
                    date_str = match.group(0)
                    try:
                        # Parse date based on format
                        if '/' in date_str or '-' in date_str:
                            if re.match(r'\d{4}', date_str):  # YYYY-MM-DD
                                date = datetime.strptime(date_str, '%Y-%m-%d')
                            else:  # DD-MM-YYYY
                                date = datetime.strptime(date_str, '%d-%m-%Y')
                        else:  # DD Month YYYY
                            date = datetime.strptime(date_str, '%d %b %Y')
                        dates.append(date)
                    except ValueError:
                        continue
            
            if len(dates) >= 2:
                return {
                    'start_date': min(dates),
                    'end_date': max(dates)
                }
                
            return None
            
        except Exception as e:
            logger.error(f"Validity period extraction error: {str(e)}")
            return None

    def extract_owner_name(self, text: str) -> Optional[str]:
        """Extract vehicle owner name from text."""
        try:
            # Look for name pattern with title
            match = re.search(self.name_pattern, text)
            if match:
                return match.group(1)
            
            # Try alternative name extraction methods
            # Look for name after "Owner:" or similar labels
            owner_labels = ['Owner:', 'Owner Name:', 'Name of Owner:', 'Registered Owner:']
            for label in owner_labels:
                pattern = f"{label}\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)"
                match = re.search(pattern, text)
                if match:
                    return match.group(1)
            
            return None
            
        except Exception as e:
            logger.error(f"Owner name extraction error: {str(e)}")
            return None

    def extract_vehicle_class(self, text: str) -> Optional[str]:
        """Extract vehicle class from text."""
        try:
            # Common vehicle class patterns
            class_patterns = [
                r'Class:\s*([A-Za-z\s]+)',
                r'Vehicle Class:\s*([A-Za-z\s]+)',
                r'Type of Vehicle:\s*([A-Za-z\s]+)'
            ]
            
            for pattern in class_patterns:
                match = re.search(pattern, text)
                if match:
                    vehicle_class = match.group(1).strip()
                    # Validate against known vehicle classes
                    if self._validate_vehicle_class(vehicle_class):
                        return vehicle_class
            
            return None
            
        except Exception as e:
            logger.error(f"Vehicle class extraction error: {str(e)}")
            return None

    def extract_insured_value(self, text: str) -> Optional[float]:
        """Extract insured value amount from text."""
        try:
            # Look for amount pattern with currency indicators
            matches = re.finditer(self.amount_pattern, text)
            amounts = []
            
            for match in matches:
                amount_str = match.group(1)
                # Remove commas and convert to float
                amount = float(amount_str.replace(',', ''))
                amounts.append(amount)
            
            if amounts:
                # Usually the highest amount is the insured value
                return max(amounts)
            
            return None
            
        except Exception as e:
            logger.error(f"Insured value extraction error: {str(e)}")
            return None

    def extract_certificate_number(self, text: str) -> Optional[str]:
        """Extract fitness certificate number from text."""
        try:
            # Common certificate number patterns
            cert_patterns = [
                r'Certificate No\.?\s*[:.]?\s*([A-Z0-9-/]+)',
                r'Cert\.\s*No\.?\s*[:.]?\s*([A-Z0-9-/]+)',
                r'Fitness Cert\.?\s*No\.?\s*[:.]?\s*([A-Z0-9-/]+)'
            ]
            
            for pattern in cert_patterns:
                match = re.search(pattern, text)
                if match:
                    return match.group(1).strip()
            
            return None
            
        except Exception as e:
            logger.error(f"Certificate number extraction error: {str(e)}")
            return None

    def extract_dates(self, text: str) -> List[datetime]:
        """Extract all dates found in text."""
        try:
            dates = []
            
            for pattern in self.date_patterns:
                matches = re.finditer(pattern, text)
                for match in matches:
                    date_str = match.group(0)
                    try:
                        # Parse date based on format
                        if '/' in date_str or '-' in date_str:
                            if re.match(r'\d{4}', date_str):
                                date = datetime.strptime(date_str, '%Y-%m-%d')
                            else:
                                date = datetime.strptime(date_str, '%d-%m-%Y')
                        else:
                            date = datetime.strptime(date_str, '%d %b %Y')
                        dates.append(date)
                    except ValueError:
                        continue
            
            return sorted(dates)
            
        except Exception as e:
            logger.error(f"Date extraction error: {str(e)}")
            return []

    def _validate_vehicle_class(self, vehicle_class: str) -> bool:
        """Validate extracted vehicle class against known classes."""
        valid_classes = {
            'LMV', 'HMV', 'MCWG', 'MGV', 'HGV',
            'LIGHT MOTOR VEHICLE',
            'HEAVY MOTOR VEHICLE',
            'MOTOR CYCLE WITH GEAR',
            'MEDIUM GOODS VEHICLE',
            'HEAVY GOODS VEHICLE'
        }
        
        # Normalize input
        normalized_class = vehicle_class.upper().strip()
        
        # Check exact matches
        if normalized_class in valid_classes:
            return True
            
        # Check partial matches
        for valid_class in valid_classes:
            if normalized_class in valid_class or valid_class in normalized_class:
                return True
                
        return False

    def extract_engine_number(self, text: str) -> Optional[str]:
        """Extract engine number from text."""
        try:
            engine_patterns = [
                r'Engine\s+No\.?\s*[:.]?\s*([A-Z0-9]+)',
                r'Engine\s+Number\s*[:.]?\s*([A-Z0-9]+)'
            ]
            
            for pattern in engine_patterns:
                match = re.search(pattern, text)
                if match:
                    return match.group(1).strip()
                    
            return None
            
        except Exception as e:
            logger.error(f"Engine number extraction error: {str(e)}")
            return None

    def extract_chassis_number(self, text: str) -> Optional[str]:
        """Extract chassis number from text."""
        try:
            chassis_patterns = [
                r'Chassis\s+No\.?\s*[:.]?\s*([A-Z0-9]+)',
                r'Chassis\s+Number\s*[:.]?\s*([A-Z0-9]+)',
                r'VIN\s*[:.]?\s*([A-Z0-9]+)'
            ]
            
            for pattern in chassis_patterns:
                match = re.search(pattern, text)
                if match:
                    chassis_num = match.group(1).strip()
                    # Validate chassis number format
                    if len(chassis_num) == 17:  # Standard VIN length
                        return chassis_num
                    
            return None
            
        except Exception as e:
            logger.error(f"Chassis number extraction error: {str(e)}")
            return None

    def clean_extracted_text(self, text: str) -> str:
        """Clean and normalize extracted text."""
        try:
            # Remove extra whitespace
            text = ' '.join(text.split())
            
            # Convert common OCR errors
            text = text.replace('0', 'O')  # Common OCR confusion
            text = text.replace('1', 'I')  # Common OCR confusion
            text = text.replace('5', 'S')  # Common OCR confusion
            
            # Remove special characters
            text = re.sub(r'[^\w\s@.,:/\-]', '', text)
            
            # Convert to uppercase for consistency
            text = text.upper()
            
            return text
            
        except Exception as e:
            logger.error(f"Text cleaning error: {str(e)}")
            return text

# Initialize text extraction helper
text_extraction_helper = TextExtractionHelper()