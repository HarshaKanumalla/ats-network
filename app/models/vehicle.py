#backend/app/models/vehicle.py


from datetime import datetime, date
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, validator
import re

from .common import TimestampedModel, PyObjectId
from ..core.constants import DocumentType

class DocumentVerification(TimestampedModel):
    """Document verification status and history."""
    
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
    
    @validator('expiry_date')
    def validate_expiry(cls, v: Optional[date], values: Dict[str, Any]) -> Optional[date]:
        """Validate document expiry date."""
        if v and v <= values['issue_date']:
            raise ValueError("Expiry date must be after issue date")
        return v

class TestHistoryEntry(BaseModel):
    """Test history record for a vehicle."""
    
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

class OwnershipRecord(TimestampedModel):
    """Vehicle ownership record."""
    
    owner_name: str
    contact_number: str
    address: str
    ownership_type: str  # individual/company/government
    registration_number: str
    transfer_date: datetime
    transfer_document_url: Optional[str] = None
    verified_by: Optional[PyObjectId] = None
    verification_status: str = "pending"

class VehicleCategory(BaseModel):
    """Vehicle category and classification."""
    
    main_category: str  # passenger/commercial/special
    sub_category: str
    seating_capacity: Optional[int] = None
    gross_weight: Optional[float] = None
    axle_configuration: Optional[str] = None
    fuel_type: str
    emission_standard: str

class Vehicle(TimestampedModel):
    """Enhanced vehicle model with comprehensive tracking."""
    
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
    
    class Config:
        """Model configuration."""
        validate_assignment = True
        json_encoders = {
            datetime: lambda dt: dt.isoformat(),
            date: lambda d: d.isoformat(),
            PyObjectId: str
        }

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

    def add_test_record(
        self,
        test_entry: TestHistoryEntry
    ) -> None:
        """Add test record with updates to related fields."""
        self.test_history.append(test_entry)
        self.last_test_date = test_entry.test_date
        self.next_test_due = test_entry.next_test_due
        self.test_status = test_entry.overall_status

    def transfer_ownership(
        self,
        new_owner: OwnershipRecord
    ) -> None:
        """Transfer vehicle ownership with history tracking."""
        if self.current_owner:
            self.ownership_history.append(self.current_owner)
        self.current_owner = new_owner

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

    def get_test_summary(self) -> Dict[str, Any]:
        """Generate test history summary."""
        if not self.test_history:
            return {"status": "no_tests"}
            
        return {
            "total_tests": len(self.test_history),
            "last_test": {
                "date": self.last_test_date,
                "status": self.test_status,
                "center_id": self.test_history[-1].center_id
            },
            "next_due": self.next_test_due,
            "test_status": self.test_status
        }