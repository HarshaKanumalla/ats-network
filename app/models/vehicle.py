from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, validator
import re
import logging

from .common import TimestampedModel, PyObjectId
from ..core.constants import DocumentType

logger = logging.getLogger(__name__)

class DocumentVerification(TimestampedModel):
    """Document verification status and history."""
    
    VALID_STATUSES = ["pending", "verified", "rejected", "expired"]
    
    document_type: DocumentType
    document_number: str
    issue_date: date
    expiry_date: Optional[date] = None
    issuing_authority: str
    
    document_url: str
    verification_status: str = "pending"
    verified_by: Optional[PyObjectId] = None
    verified_at: Optional[datetime] = None
    verification_notes: Optional[str] = None
    
    renewal_reminder_sent: bool = False
    last_reminder_date: Optional[datetime] = None
    
    @validator('verification_status')
    def validate_status(cls, v: str) -> str:
        if v not in cls.VALID_STATUSES:
            raise ValueError(f"Invalid status. Must be one of: {cls.VALID_STATUSES}")
        return v

    @validator('expiry_date')
    def validate_expiry(cls, v: Optional[date], values: Dict[str, Any]) -> Optional[date]:
        """Validate document expiry date."""
        if v and v <= values['issue_date']:
            raise ValueError("Expiry date must be after issue date")
        return v

class TestHistoryEntry(BaseModel):
    """Test history record for a vehicle."""
    
    VALID_STATUSES = ["pass", "fail", "incomplete", "cancelled"]
    
    test_session_id: PyObjectId
    test_date: datetime
    center_id: PyObjectId
    test_types: List[str]
    results: Dict[str, Any]
    overall_status: str
    certificate_number: Optional[str] = None
    certificate_url: Optional[str] = None
    next_test_due: Optional[datetime] = None
    inspector_notes: Optional[str] = None

    @validator('overall_status')
    def validate_status(cls, v: str) -> str:
        if v not in cls.VALID_STATUSES:
            raise ValueError(f"Invalid status. Must be one of: {cls.VALID_STATUSES}")
        return v

    def calculate_next_test_due(self) -> datetime:
        """Calculate next test due date based on test type and results."""
        base_date = self.test_date
        if self.overall_status == "pass":
            if "annual" in self.test_types:
                return base_date + timedelta(days=365)
            elif "quarterly" in self.test_types:
                return base_date + timedelta(days=90)
            elif "monthly" in self.test_types:
                return base_date + timedelta(days=30)
        return base_date + timedelta(days=30)  # Default for failed tests

class OwnershipRecord(TimestampedModel):
    """Vehicle ownership record."""
    
    VALID_OWNERSHIP_TYPES = ["individual", "company", "government"]
    VALID_STATUSES = ["pending", "verified", "rejected"]
    
    owner_name: str
    contact_number: str
    address: str
    ownership_type: str
    registration_number: str
    transfer_date: datetime
    transfer_document_url: Optional[str] = None
    verified_by: Optional[PyObjectId] = None
    verification_status: str = "pending"

    @validator('ownership_type')
    def validate_ownership_type(cls, v: str) -> str:
        if v not in cls.VALID_OWNERSHIP_TYPES:
            raise ValueError(f"Invalid ownership type. Must be one of: {cls.VALID_OWNERSHIP_TYPES}")
        return v

    @validator('verification_status')
    def validate_status(cls, v: str) -> str:
        if v not in cls.VALID_STATUSES:
            raise ValueError(f"Invalid status. Must be one of: {cls.VALID_STATUSES}")
        return v

class VehicleCategory(BaseModel):
    """Vehicle category and classification."""
    
    VALID_MAIN_CATEGORIES = ["passenger", "commercial", "special"]
    VALID_FUEL_TYPES = ["petrol", "diesel", "cng", "electric", "hybrid"]
    
    main_category: str
    sub_category: str
    seating_capacity: Optional[int] = None
    gross_weight: Optional[float] = None
    axle_configuration: Optional[str] = None
    fuel_type: str
    emission_standard: str

    @validator('main_category')
    def validate_category(cls, v: str) -> str:
        if v not in cls.VALID_MAIN_CATEGORIES:
            raise ValueError(f"Invalid category. Must be one of: {cls.VALID_MAIN_CATEGORIES}")
        return v

    @validator('fuel_type')
    def validate_fuel(cls, v: str) -> str:
        if v not in cls.VALID_FUEL_TYPES:
            raise ValueError(f"Invalid fuel type. Must be one of: {cls.VALID_FUEL_TYPES}")
        return v

class Vehicle(TimestampedModel):
    """Enhanced vehicle model with comprehensive tracking."""
    
    VALID_STATUSES = [
        "active", "inactive", "suspended", "retired", 
        "maintenance", "blacklisted"
    ]
    
    registration_number: str = Field(..., regex=r'^[A-Z]{2}[0-9]{2}[A-Z]{1,2}[0-9]{4}$')
    chassis_number: str = Field(..., min_length=17, max_length=17)
    engine_number: str
    model_name: str
    manufacturer: str
    manufacturing_year: int
    
    category: VehicleCategory
    registered_center: PyObjectId
    
    # Document management
    documents: Dict[str, DocumentVerification] = {}
    document_history: List[Dict[str, Any]] = []
    
    # Test history
    test_history: List[TestHistoryEntry] = []
    last_test_date: Optional[datetime] = None
    next_test_due: Optional[datetime] = None
    test_status: str = "pending"
    
    # Ownership tracking
    current_owner: OwnershipRecord
    ownership_history: List[OwnershipRecord] = []
    
    # Status tracking
    status: str = "active"
    status_history: List[Dict[str, Any]] = []
    last_status_change: Optional[datetime] = None

    @validator('status')
    def validate_status(cls, v: str) -> str:
        if v not in cls.VALID_STATUSES:
            raise ValueError(f"Invalid status. Must be one of: {cls.VALID_STATUSES}")
        return v

    @validator('manufacturing_year')
    def validate_year(cls, v: int) -> int:
        """Validate manufacturing year."""
        current_year = datetime.now().year
        if not 1900 <= v <= current_year:
            raise ValueError(f"Year must be between 1900 and {current_year}")
        return v

    def add_document(
        self,
        document_type: DocumentType,
        document_data: Dict[str, Any]
    ) -> None:
        """Add new document with history tracking."""
        if document_type in self.documents:
            # Archive old document
            old_doc = self.documents[document_type]
            self.document_history.append({
                **old_doc.dict(),
                "archived_at": datetime.utcnow()
            })
        
        self.documents[document_type] = DocumentVerification(**document_data)
        logger.info(f"Document added: {document_type} for vehicle {self.registration_number}")

    def check_document_expiry(self) -> List[Dict[str, Any]]:
        """Check for documents nearing expiry."""
        expiring_docs = []
        current_date = datetime.utcnow().date()
        warning_threshold = timedelta(days=30)
        
        for doc_type, doc in self.documents.items():
            if doc.expiry_date:
                days_remaining = (doc.expiry_date - current_date).days
                if 0 < days_remaining <= warning_threshold.days:
                    expiring_docs.append({
                        "document_type": doc_type,
                        "expiry_date": doc.expiry_date,
                        "days_remaining": days_remaining
                    })
        return expiring_docs

    def update_status(
        self,
        new_status: str,
        reason: str,
        updated_by: PyObjectId
    ) -> None:
        """Update vehicle status with history tracking."""
        if new_status == self.status:
            return
            
        self.status_history.append({
            "previous_status": self.status,
            "new_status": new_status,
            "reason": reason,
            "updated_by": updated_by,
            "updated_at": datetime.utcnow()
        })
        
        self.status = new_status
        self.last_status_change = datetime.utcnow()
        logger.info(f"Status updated to {new_status} for vehicle {self.registration_number}")

    def add_test_record(
        self,
        test_entry: TestHistoryEntry
    ) -> None:
        """Add test record with updates to related fields."""
        self.test_history.append(test_entry)
        self.last_test_date = test_entry.test_date
        self.next_test_due = test_entry.calculate_next_test_due()
        self.test_status = test_entry.overall_status
        logger.info(f"Test record added for vehicle {self.registration_number}")

    def transfer_ownership(
        self,
        new_owner: OwnershipRecord
    ) -> None:
        """Transfer vehicle ownership with history tracking."""
        if self.current_owner:
            self.ownership_history.append(self.current_owner)
        self.current_owner = new_owner
        logger.info(f"Ownership transferred for vehicle {self.registration_number}")

    def check_document_validity(self) -> Dict[str, bool]:
        """Check validity of all documents."""
        current_date = datetime.utcnow().date()
        return {
            doc_type: (
                doc.verification_status == "verified" and
                (doc.expiry_date is None or doc.expiry_date > current_date)
            )
            for doc_type, doc in self.documents.items()
        }

    def collect_vehicle_metrics(self) -> Dict[str, Any]:
        """Collect comprehensive vehicle metrics."""
        current_date = datetime.utcnow().date()
        
        return {
            "document_metrics": {
                "total_documents": len(self.documents),
                "valid_documents": sum(1 for doc in self.documents.values() 
                                    if doc.verification_status == "verified"),
                "expiring_soon": len(self.check_document_expiry())
            },
            "test_metrics": {
                "total_tests": len(self.test_history),
                "pass_rate": sum(1 for test in self.test_history 
                               if test.overall_status == "pass") / len(self.test_history)
                if self.test_history else 0,
                "last_test_status": self.test_status,
                "days_to_next_test": (self.next_test_due - datetime.utcnow()).days
                if self.next_test_due else None
            },
            "ownership_metrics": {
                "total_transfers": len(self.ownership_history),
                "current_owner_verified": self.current_owner.verification_status == "verified"
            },
            "status_metrics": {
                "current_status": self.status,
                "status_changes": len(self.status_history),
                "days_in_current_status": (current_date - self.last_status_change.date()).days
                if self.last_status_change else 0
            }
        }

    class Config:
        """Model configuration."""
        validate_assignment = True
        json_encoders = {
            datetime: lambda dt: dt.isoformat(),
            date: lambda d: d.isoformat(),
            PyObjectId: str
        }