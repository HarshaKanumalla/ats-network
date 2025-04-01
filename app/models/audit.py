from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field, validator
import hashlib
import logging
from pathlib import Path

from .common import TimestampedModel, PyObjectId

logger = logging.getLogger(__name__)

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

    @classmethod
    def _missing_(cls, value):
        """Handle case-insensitive lookup."""
        for member in cls:
            if member.value.lower() == str(value).lower():
                return member
        return None

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

    @classmethod
    def _missing_(cls, value):
        """Handle case-insensitive lookup."""
        for member in cls:
            if member.value.lower() == str(value).lower():
                return member
        return None

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

    @validator('change_type')
    def validate_change_type(cls, v):
        valid_types = ['modified', 'added', 'removed']
        if v not in valid_types:
            raise ValueError(f"Invalid change type. Must be one of: {valid_types}")
        return v

class SecurityContext(BaseModel):
    """Security context information for audit events."""
    ip_address: str
    user_agent: str
    session_id: Optional[str]
    authentication_method: str
    permissions_used: List[str] = []
    geo_location: Optional[Dict[str, Any]] = None

    @validator('ip_address', 'user_agent')
    def validate_required_fields(cls, v):
        if not v:
            raise ValueError("This field is required")
        return v

class ComplianceMetadata(BaseModel):
    """Compliance-related metadata for audit events."""
    regulation_references: List[str] = []
    compliance_requirements: List[str] = []
    retention_period: Optional[str] = None
    data_classification: Optional[str] = None
    verification_status: Optional[str] = None

    @validator('retention_period')
    def validate_retention_period(cls, v):
        if v:
            valid_units = ["days", "months", "years"]
            try:
                value, unit = v.split()
                if not (value.isdigit() and int(value) > 0 and unit in valid_units):
                    raise ValueError
            except ValueError:
                raise ValueError("Invalid retention period format")
        return v

class AuditEvent(TimestampedModel):
    """Comprehensive audit event record."""
    event_id: str = Field(..., regex=r'^AUD\d{14}$')
    category: AuditCategory
    action: AuditAction
    status: str = "completed"
    
    actor_id: PyObjectId
    actor_role: str
    impersonator_id: Optional[PyObjectId] = None
    
    entity_type: EntityType
    entity_id: str
    entity_name: Optional[str] = None
    
    description: str
    changes: List[DataChange] = []
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    security_context: SecurityContext
    compliance_metadata: ComplianceMetadata
    
    related_events: List[str] = []
    parent_event_id: Optional[str] = None
    error_details: Optional[Dict[str, Any]] = None

    @validator('actor_id', 'entity_id', 'description')
    def validate_required_fields(cls, v):
        if not v:
            raise ValueError("This field is required")
        return v

    @validator('changes')
    def validate_changes(cls, v):
        if len(v) > 100:
            raise ValueError("Too many changes in single event")
        return v

    class Config:
        validate_assignment = True
        json_encoders = {
            datetime: lambda dt: dt.isoformat(),
            PyObjectId: str
        }

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

    @validator('last_event')
    def validate_event_dates(cls, v, values):
        if 'first_event' in values and v < values['first_event']:
            raise ValueError("Last event cannot be before first event")
        return v

    def export_to_dict(self) -> Dict[str, Any]:
        """Export audit trail to dictionary format."""
        try:
            export_data = {
                "entity_type": self.entity_type,
                "entity_id": self.entity_id,
                "entity_name": self.entity_name,
                "events": [event.dict() for event in self.events],
                "first_event": self.first_event.isoformat(),
                "last_event": self.last_event.isoformat(),
                "event_count": self.event_count,
                "actor_count": self.actor_count,
                "unique_actors": self.unique_actors,
                "compliance_status": self.compliance_status,
                "compliance_violations": self.compliance_violations
            }
            logger.info(f"Successfully exported audit trail for {self.entity_type}:{self.entity_id}")
            return export_data
        except Exception as e:
            logger.error(f"Failed to export audit trail: {str(e)}")
            raise ValueError("Failed to export audit trail") from e

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
        try:
            if not self.findings:
                return {
                    "risk_levels": {"high": 0, "medium": 0, "low": 0},
                    "high_risk_percentage": 0,
                    "compliance_score": self.compliance_score,
                    "violation_rate": 0
                }

            risk_levels = {"high": 0, "medium": 0, "low": 0}
            for finding in self.findings:
                risk_level = finding.get("risk_level", "low").lower()
                if risk_level not in risk_levels:
                    raise ValueError(f"Invalid risk level: {risk_level}")
                risk_levels[risk_level] += 1

            total_findings = len(self.findings)
            metrics = {
                "risk_levels": risk_levels,
                "high_risk_percentage": (risk_levels["high"] / total_findings) * 100,
                "compliance_score": self.compliance_score,
                "violation_rate": (self.violations_found / max(self.events_analyzed, 1)) * 100
            }
            logger.info(f"Risk metrics calculated for report {self.report_id}")
            return metrics
        except Exception as e:
            logger.error(f"Error calculating risk metrics: {str(e)}")
            raise ValueError("Failed to calculate risk metrics") from e

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
        try:
            archive_path = Path(self.storage_location)
            if not archive_path.exists():
                raise FileNotFoundError(f"Archive not found: {self.storage_location}")
                
            hasher = hashlib.sha256()
            with archive_path.open('rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    hasher.update(chunk)
                    
            calculated_hash = hasher.hexdigest()
            integrity_verified = calculated_hash == self.hash_value
            
            if integrity_verified:
                logger.info(f"Archive integrity verified: {self.archive_id}")
            else:
                logger.warning(f"Archive integrity check failed: {self.archive_id}")
                
            return integrity_verified
        except Exception as e:
            logger.error(f"Archive integrity check failed: {str(e)}")
            return False

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
            "issues": [],
            "warnings": []
        }
        
        # Validate categories
        if not self.enabled_categories:
            validation_results["valid"] = False
            validation_results["issues"].append("No audit categories enabled")
        
        # Validate retention periods
        for category, period in self.retention_periods.items():
            if not self._validate_retention_period(period):
                validation_results["valid"] = False
                validation_results["issues"].append(
                    f"Invalid retention period for {category}: {period}"
                )
        
        # Validate encryption settings
        required_encryption_settings = ["algorithm", "key_size", "mode"]
        for setting in required_encryption_settings:
            if setting not in self.encryption_settings:
                validation_results["valid"] = False
                validation_results["issues"].append(
                    f"Missing required encryption setting: {setting}"
                )
        
        # Storage validation
        if not self.storage_settings.get("location"):
            validation_results["warnings"].append(
                "Storage location not specified"
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