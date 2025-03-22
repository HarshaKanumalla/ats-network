#backend/app/models/audit.py

from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field, validator

from .common import TimestampedModel, PyObjectId

class AuditCategory(str, Enum):
    """Categories for audit events."""
    USER_MANAGEMENT = "user_management"
    CENTER_OPERATIONS = "center_operations"
    TEST_OPERATIONS = "test_operations"
    VEHICLE_MANAGEMENT = "vehicle_management"
    SYSTEM_CONFIGURATION = "system_configuration"
    SECURITY = "security"
    COMPLIANCE = "compliance"
    DATA_ACCESS = "data_access"

class AuditAction(str, Enum):
    """Specific actions for audit tracking."""
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    ACCESS = "access"
    APPROVE = "approve"
    REJECT = "reject"
    LOGIN = "login"
    LOGOUT = "logout"
    EXPORT = "export"
    CONFIGURE = "configure"

class EntityType(str, Enum):
    """Types of entities being audited."""
    USER = "user"
    CENTER = "center"
    VEHICLE = "vehicle"
    TEST_SESSION = "test_session"
    REPORT = "report"
    CONFIGURATION = "configuration"
    DOCUMENT = "document"
    PERMISSION = "permission"

class DataChange(BaseModel):
    """Record of data changes in an audit event."""
    
    field_name: str
    old_value: Optional[Any]
    new_value: Optional[Any]
    change_type: str  # modified/added/removed
    field_path: Optional[str] = None
    validation_status: Optional[str] = None

class SecurityContext(BaseModel):
    """Security context information for audit events."""
    
    ip_address: str
    user_agent: str
    session_id: Optional[str]
    authentication_method: str
    permissions_used: List[str] = []
    geo_location: Optional[Dict[str, Any]] = None

class ComplianceMetadata(BaseModel):
    """Compliance-related metadata for audit events."""
    
    regulation_references: List[str] = []
    compliance_requirements: List[str] = []
    retention_period: Optional[str] = None
    data_classification: Optional[str] = None
    verification_status: Optional[str] = None

class AuditEvent(TimestampedModel):
    """Comprehensive audit event record."""
    
    event_id: str = Field(..., regex=r'^AUD\d{14}$')
    category: AuditCategory
    action: AuditAction
    status: str = "completed"
    
    # Actor information
    actor_id: PyObjectId
    actor_role: str
    impersonator_id: Optional[PyObjectId] = None
    
    # Target information
    entity_type: EntityType
    entity_id: str
    entity_name: Optional[str] = None
    
    # Event details
    description: str
    changes: List[DataChange] = []
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    # Security context
    security_context: SecurityContext
    
    # Compliance information
    compliance_metadata: ComplianceMetadata
    
    # Related information
    related_events: List[str] = []
    parent_event_id: Optional[str] = None
    
    # Error tracking
    error_details: Optional[Dict[str, Any]] = None
    
    class Config:
        """Model configuration."""
        validate_assignment = True
        json_encoders = {
            datetime: lambda dt: dt.isoformat(),
            PyObjectId: str
        }

    @validator('event_id')
    def validate_event_id(cls, v: str) -> str:
        """Validate audit event ID format."""
        if not v.startswith('AUD'):
            raise ValueError("Event ID must start with 'AUD'")
        try:
            datetime.strptime(v[3:], '%Y%m%d%H%M%S')
        except ValueError:
            raise ValueError("Invalid event ID timestamp format")
        return v

class AuditLogQuery(BaseModel):
    """Query parameters for searching audit logs."""
    
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    categories: Optional[List[AuditCategory]] = None
    actions: Optional[List[AuditAction]] = None
    entity_types: Optional[List[EntityType]] = None
    actor_id: Optional[PyObjectId] = None
    entity_id: Optional[str] = None
    status: Optional[str] = None
    compliance_refs: Optional[List[str]] = None

class AuditTrail(BaseModel):
    """Complete audit trail for an entity."""
    
    entity_type: EntityType
    entity_id: str
    entity_name: Optional[str] = None
    
    events: List[AuditEvent]
    first_event: datetime
    last_event: datetime
    
    event_count: int
    actor_count: int
    unique_actors: List[Dict[str, Any]]
    
    compliance_status: Optional[str] = None
    compliance_violations: List[Dict[str, Any]] = []

class ComplianceReport(TimestampedModel):
    """Compliance audit report."""
    
    report_id: str
    report_type: str
    period_start: datetime
    period_end: datetime
    
    regulations: List[str]
    audit_criteria: Dict[str, Any]
    
    events_analyzed: int
    compliance_score: float
    violations_found: int
    
    findings: List[Dict[str, Any]]
    recommendations: List[str]
    
    generated_by: PyObjectId
    approved_by: Optional[PyObjectId] = None
    
    def calculate_risk_metrics(self) -> Dict[str, Any]:
        """Calculate risk metrics from audit findings."""
        risk_levels = {"high": 0, "medium": 0, "low": 0}
        for finding in self.findings:
            risk_level = finding.get("risk_level", "low")
            risk_levels[risk_level] += 1
            
        return {
            "risk_levels": risk_levels,
            "high_risk_percentage": (risk_levels["high"] / len(self.findings)) * 100,
            "compliance_score": self.compliance_score,
            "violation_rate": (self.violations_found / self.events_analyzed) * 100
        }

class AuditArchive(TimestampedModel):
    """Archive of audit events for long-term storage."""
    
    archive_id: str
    period_start: datetime
    period_end: datetime
    
    event_count: int
    file_size: int
    storage_location: str
    
    compression_method: str
    encryption_method: str
    hash_value: str
    
    retention_period: str
    deletion_date: Optional[datetime] = None
    
    def verify_integrity(self) -> bool:
        """Verify archive integrity using stored hash."""
        return True  # Implementation would verify actual hash

class AuditConfiguration(BaseModel):
    """Audit system configuration settings."""
    
    enabled_categories: List[AuditCategory]
    retention_periods: Dict[AuditCategory, str]
    compliance_requirements: Dict[str, List[str]]
    
    archival_settings: Dict[str, Any]
    alert_thresholds: Dict[str, Any]
    
    encryption_settings: Dict[str, Any]
    storage_settings: Dict[str, Any]
    
    def validate_configuration(self) -> Dict[str, Any]:
        """Validate configuration settings."""
        validation_results = {
            "valid": True,
            "issues": []
        }
        
        # Validate retention periods
        for category, period in self.retention_periods.items():
            if not self._validate_retention_period(period):
                validation_results["valid"] = False
                validation_results["issues"].append(
                    f"Invalid retention period for {category}: {period}"
                )
        
        return validation_results

    def _validate_retention_period(self, period: str) -> bool:
        """Validate retention period format."""
        valid_units = ["days", "months", "years"]
        try:
            value, unit = period.split()
            return (
                value.isdigit() and
                int(value) > 0 and
                unit in valid_units
            )
        except ValueError:
            return False