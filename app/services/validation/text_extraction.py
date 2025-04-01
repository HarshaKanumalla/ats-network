import re
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
import logging
import json
from dataclasses import dataclass

from ...core.exceptions import ExtractionError
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

@dataclass
class ExtractionResult:
    """Data class for extraction results."""
    value: Any
    confidence: float
    method: str
    source_text: str

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
        
        # Name patterns
        self.name_pattern = r'(?:Mr\.|Mrs\.|Ms\.|Dr\.)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)'
        
        # Vehicle identification patterns
        self.vin_pattern = r'[A-HJ-NPR-Z0-9]{17}'
        self.engine_pattern = r'[A-Z0-9]{6,12}'

        # Additional patterns
        self.chassis_pattern = r'(?:Chassis|Frame)\s*(?:No\.?|Number)?\s*:?\s*([A-Z0-9]{12,17})'
        self.phone_pattern = r'(?:Phone|Mobile|Tel)[.:]\s*(?:\+91[-\s]?)?(\d{10})'
        self.email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        self.address_pattern = r'(?:Address|Location)\s*:?\s*([^.]*(?:\.\s*[^.]*){0,2}\.?)'
        
        # Initialize OCR corrections
        self._initialize_ocr_corrections()
        
        logger.info("Text extraction helper initialized with enhanced patterns")

    def _initialize_ocr_corrections(self):
        """Initialize OCR correction mappings."""
        self.ocr_corrections = {
            # Common OCR errors
            '0': 'O',
            '1': 'I',
            '5': 'S',
            '8': 'B',
            '@': 'A',
            # Special characters
            '|': 'I',
            '[': 'I',
            ']': 'I',
            '{': 'I',
            '}': 'I',
            # Additional corrections
            'é': 'e',
            'è': 'e',
            'ñ': 'n',
            'ü': 'u',
            'ö': 'o',
            'ä': 'a'
        }

    def preprocess_text(self, text: str) -> str:
        """Preprocess text for better extraction accuracy."""
        try:
            # Convert to uppercase
            text = text.upper()
            
            # Apply OCR corrections
            for wrong, correct in self.ocr_corrections.items():
                text = text.replace(wrong, correct)
            
            # Normalize whitespace
            text = ' '.join(text.split())
            
            # Standardize separators
            text = re.sub(r'[;|]', ':', text)
            text = re.sub(r'[\(\)\[\]]', '', text)
            
            # Remove unwanted characters
            text = re.sub(r'[^\w\s@.,:/\-]', '', text)
            
            return text
            
        except Exception as e:
            logger.error(f"Text preprocessing error: {str(e)}")
            raise ExtractionError(f"Failed to preprocess text: {str(e)}")

    def extract_registration_number(self, text: str) -> ExtractionResult:
        """Extract vehicle registration number from text."""
        try:
            text = self.preprocess_text(text)
            matches = re.findall(self.reg_number_pattern, text)
            
            if matches:
                reg_number = matches[0]
                reg_number = re.sub(r'\s+', '', reg_number)
                confidence = 1.0 if len(reg_number) == 10 else 0.8
                
                return ExtractionResult(
                    value=reg_number,
                    confidence=confidence,
                    method="regex_pattern",
                    source_text=matches[0]
                )
            
            return ExtractionResult(
                value=None,
                confidence=0.0,
                method="regex_pattern",
                source_text=""
            )
            
        except Exception as e:
            logger.error(f"Registration number extraction error: {str(e)}")
            raise ExtractionError(f"Failed to extract registration number: {str(e)}")

    def extract_policy_number(self, text: str) -> ExtractionResult:
        """Extract insurance policy number from text."""
        try:
            text = self.preprocess_text(text)
            
            # Try specific company patterns first
            for company, pattern in self.policy_patterns['specific'].items():
                match = re.search(pattern, text)
                if match:
                    return ExtractionResult(
                        value=match.group(0),
                        confidence=0.9,
                        method=f"specific_pattern_{company}",
                        source_text=match.group(0)
                    )
            
            # Try general pattern
            match = re.search(self.policy_patterns['general'], text)
            if match:
                return ExtractionResult(
                    value=match.group(1),
                    confidence=0.7,
                    method="general_pattern",
                    source_text=match.group(0)
                )
            
            return ExtractionResult(
                value=None,
                confidence=0.0,
                method="no_match",
                source_text=""
            )
            
        except Exception as e:
            logger.error(f"Policy number extraction error: {str(e)}")
            raise ExtractionError(f"Failed to extract policy number: {str(e)}")

    def extract_date(self, text: str) -> ExtractionResult:
        """Extract date from text."""
        try:
            text = self.preprocess_text(text)
            
            for pattern in self.date_patterns:
                matches = re.findall(pattern, text)
                if matches:
                    try:
                        date_str = matches[0]
                        date = datetime.strptime(date_str, self._get_date_format(date_str))
                        
                        return ExtractionResult(
                            value=date,
                            confidence=0.9,
                            method="date_pattern",
                            source_text=date_str
                        )
                    except ValueError:
                        continue
            
            return ExtractionResult(
                value=None,
                confidence=0.0,
                method="date_pattern",
                source_text=""
            )
            
        except Exception as e:
            logger.error(f"Date extraction error: {str(e)}")
            raise ExtractionError(f"Failed to extract date: {str(e)}")

    def _get_date_format(self, date_str: str) -> str:
        """Determine date string format."""
        if re.match(r'\d{2}[-/]\d{2}[-/]\d{4}', date_str):
            return '%d-%m-%Y' if '-' in date_str else '%d/%m/%Y'
        elif re.match(r'\d{4}[-/]\d{2}[-/]\d{2}', date_str):
            return '%Y-%m-%d' if '-' in date_str else '%Y/%m/%d'
        else:
            return '%d %b %Y'

    def extract_amount(self, text: str) -> ExtractionResult:
        """Extract monetary amount from text."""
        try:
            text = self.preprocess_text(text)
            match = re.search(self.amount_pattern, text)
            
            if match:
                amount_str = match.group(1).replace(',', '')
                amount = float(amount_str)
                
                return ExtractionResult(
                    value=amount,
                    confidence=0.9,
                    method="amount_pattern",
                    source_text=match.group(0)
                )
            
            return ExtractionResult(
                value=None,
                confidence=0.0,
                method="amount_pattern",
                source_text=""
            )
            
        except Exception as e:
            logger.error(f"Amount extraction error: {str(e)}")
            raise ExtractionError(f"Failed to extract amount: {str(e)}")

    def extract_name(self, text: str) -> ExtractionResult:
        """Extract person name from text."""
        try:
            text = self.preprocess_text(text)
            match = re.search(self.name_pattern, text)
            
            if match:
                name = match.group(1).strip()
                name_parts = name.split()
                confidence = 0.7 + (0.1 * len(name_parts)) if len(name_parts) <= 3 else 1.0
                
                return ExtractionResult(
                    value=name,
                    confidence=confidence,
                    method="name_pattern",
                    source_text=match.group(0)
                )
            
            return ExtractionResult(
                value=None,
                confidence=0.0,
                method="name_pattern",
                source_text=""
            )
            
        except Exception as e:
            logger.error(f"Name extraction error: {str(e)}")
            raise ExtractionError(f"Failed to extract name: {str(e)}")

    def extract_vehicle_identifiers(self, text: str) -> Dict[str, ExtractionResult]:
        """Extract vehicle identification numbers (VIN, engine, chassis)."""
        try:
            text = self.preprocess_text(text)
            results = {}
            
            # Extract VIN
            vin_match = re.search(self.vin_pattern, text)
            if vin_match:
                results['vin'] = ExtractionResult(
                    value=vin_match.group(0),
                    confidence=1.0 if len(vin_match.group(0)) == 17 else 0.8,
                    method="vin_pattern",
                    source_text=vin_match.group(0)
                )
            
            # Extract engine number
            engine_match = re.search(self.engine_pattern, text)
            if engine_match:
                results['engine'] = ExtractionResult(
                    value=engine_match.group(0),
                    confidence=0.9 if len(engine_match.group(0)) >= 8 else 0.7,
                    method="engine_pattern",
                    source_text=engine_match.group(0)
                )
            
            # Extract chassis number
            chassis_match = re.search(self.chassis_pattern, text)
            if chassis_match:
                results['chassis'] = ExtractionResult(
                    value=chassis_match.group(1),
                    confidence=0.9 if len(chassis_match.group(1)) >= 12 else 0.7,
                    method="chassis_pattern",
                    source_text=chassis_match.group(0)
                )
            
            return results
            
        except Exception as e:
            logger.error(f"Vehicle identifier extraction error: {str(e)}")
            raise ExtractionError(f"Failed to extract vehicle identifiers: {str(e)}")

    def extract_contact_info(self, text: str) -> Dict[str, ExtractionResult]:
        """Extract contact information (phone, email, address)."""
        try:
            text = self.preprocess_text(text)
            results = {}
            
            # Extract phone number
            phone_match = re.search(self.phone_pattern, text)
            if phone_match:
                results['phone'] = ExtractionResult(
                    value=phone_match.group(1),
                    confidence=0.9,
                    method="phone_pattern",
                    source_text=phone_match.group(0)
                )
            
            # Extract email
            email_match = re.search(self.email_pattern, text)
            if email_match:
                results['email'] = ExtractionResult(
                    value=email_match.group(0).lower(),
                    confidence=1.0,
                    method="email_pattern",
                    source_text=email_match.group(0)
                )
            
            # Extract address
            address_match = re.search(self.address_pattern, text)
            if address_match:
                address = address_match.group(1).strip()
                results['address'] = ExtractionResult(
                    value=address,
                    confidence=0.8,
                    method="address_pattern",
                    source_text=address_match.group(0)
                )
            
            return results
            
        except Exception as e:
            logger.error(f"Contact info extraction error: {str(e)}")
            raise ExtractionError(f"Failed to extract contact information: {str(e)}")

    def extract_with_context(
        self,
        text: str,
        field_name: str,
        context_lines: int = 2
    ) -> ExtractionResult:
        """Extract field value with surrounding context."""
        try:
            text = self.preprocess_text(text)
            lines = text.split('\n')
            
            for i, line in enumerate(lines):
                if field_name.upper() in line:
                    start = max(0, i - context_lines)
                    end = min(len(lines), i + context_lines + 1)
                    context = '\n'.join(lines[start:end])
                    
                    pattern = f"{field_name}\\s*:?\\s*([^\\n]+)"
                    match = re.search(pattern, context, re.IGNORECASE)
                    
                    if match:
                        return ExtractionResult(
                            value=match.group(1).strip(),
                            confidence=0.8,
                            method="context_extraction",
                            source_text=context
                        )
            
            return ExtractionResult(
                value=None,
                confidence=0.0,
                method="context_extraction",
                source_text=""
            )
            
        except Exception as e:
            logger.error(f"Context extraction error: {str(e)}")
            raise ExtractionError(f"Failed to extract {field_name} with context: {str(e)}")

    def validate_extraction(self, result: ExtractionResult) -> bool:
        """Validate extraction result."""
        try:
            if not result.value:
                return False
            
            if result.confidence < 0.5:
                return False
            
            # Additional validation based on method
            if result.method.startswith("specific_pattern"):
                return len(str(result.value)) >= 8
            
            if result.method == "context_extraction":
                return len(str(result.value)) >= 3
            
            if result.method == "date_pattern":
                if isinstance(result.value, datetime):
                    return result.value.year >= 1900
            
            if result.method == "amount_pattern":
                return float(result.value) > 0
            
            return True
            
        except Exception as e:
            logger.error(f"Validation error: {str(e)}")
            return False

# Initialize text extraction helper
text_extraction_helper = TextExtractionHelper()