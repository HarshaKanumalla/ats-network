from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field, validator, field_validator
from enum import Enum
import logging

from .common import TimestampedModel, PyObjectId
from ..core.constants import UserRole

logger = logging.getLogger(__name__)

class ReportType(str, Enum):
    """Report type definitions."""
    TEST_REPORT = "test_report"
    CENTER_PERFORMANCE = "center_performance"
    VEHICLE_HISTORY = "vehicle_history"
    SYSTEM_ANALYTICS = "system_analytics"
    COMPLIANCE_REPORT = "compliance_report"
    AUDIT_REPORT = "audit_report"

    @classmethod
    def validate_permissions(cls, report_type: str, user_role: UserRole) -> bool:
        """Validate user permissions for report type."""
        permissions_map = {
            cls.TEST_REPORT: [UserRole.ADMIN, UserRole.CENTER_MANAGER],
            cls.CENTER_PERFORMANCE: [UserRole.ADMIN],
            cls.VEHICLE_HISTORY: [UserRole.ADMIN, UserRole.CENTER_MANAGER],
            cls.SYSTEM_ANALYTICS: [UserRole.ADMIN],
            cls.COMPLIANCE_REPORT: [UserRole.ADMIN, UserRole.AUDITOR],
            cls.AUDIT_REPORT: [UserRole.ADMIN, UserRole.AUDITOR]
        }
        return user_role in permissions_map.get(report_type, [])

class ReportFormat(str, Enum):
    """Report output format options."""
    PDF = "pdf"
    EXCEL = "excel"
    HTML = "html"
    JSON = "json"

    @classmethod
    def get_mime_type(cls, format: 'ReportFormat') -> str:
        """Get MIME type for report format."""
        mime_types = {
            cls.PDF: "application/pdf",
            cls.EXCEL: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            cls.HTML: "text/html",
            cls.JSON: "application/json"
        }
        return mime_types.get(format, "application/octet-stream")

class ReportSection(BaseModel):
    """Individual report section definition."""
    
    VALID_SECTION_TYPES = ["table", "chart", "summary", "detail", "metrics"]
    VALID_DATA_SOURCES = ["database", "api", "file", "calculation"]
    
    title: str
    section_type: str
    content_template: str
    data_source: str
    parameters: Dict[str, Any]
    required_permissions: List[str] = []
    validation_rules: Optional[Dict[str, Any]] = None
    display_order: int

    @field_validator('section_type')
    def validate_section_type(cls, v: str) -> str:
        if v not in cls.VALID_SECTION_TYPES:
            raise ValueError(f"Invalid section type. Must be one of: {cls.VALID_SECTION_TYPES}")
        return v

    @field_validator('data_source')
    def validate_data_source(cls, v: str) -> str:
        if v not in cls.VALID_DATA_SOURCES:
            raise ValueError(f"Invalid data source. Must be one of: {cls.VALID_DATA_SOURCES}")
        return v

    def validate_parameters(self) -> List[str]:
        """Validate section parameters against rules."""
        errors = []
        if self.validation_rules:
            for param, rules in self.validation_rules.items():
                if param not in self.parameters:
                    if rules.get("required", False):
                        errors.append(f"Missing required parameter: {param}")
                else:
                    value = self.parameters[param]
                    if "type" in rules and not isinstance(value, rules["type"]):
                        errors.append(f"Invalid type for {param}")
                    if "min" in rules and value < rules["min"]:
                        errors.append(f"{param} below minimum value")
                    if "max" in rules and value > rules["max"]:
                        errors.append(f"{param} exceeds maximum value")
        return errors

class ReportTemplate(TimestampedModel):
    """Report template configuration."""
    
    template_name: str
    description: str
    report_type: ReportType
    version: str = "1.0.0"
    
    sections: List[ReportSection]
    default_format: ReportFormat = ReportFormat.PDF
    supported_formats: List[ReportFormat]
    
    header_template: Optional[str] = None
    footer_template: Optional[str] = None
    style_config: Dict[str, Any] = Field(default_factory=dict)
    
    metadata_fields: List[str] = []
    required_permissions: List[str] = []
    
    is_active: bool = True
    last_modified_by: PyObjectId
    usage_count: int = 0

    def increment_usage(self) -> None:
        """Increment template usage count."""
        self.usage_count += 1
        logger.info(f"Template {self.template_name} usage count: {self.usage_count}")

    def validate_format(self, format: ReportFormat) -> bool:
        """Validate if format is supported by template."""
        return format in self.supported_formats

    def get_section_by_title(self, title: str) -> Optional[ReportSection]:
        """Get section by title."""
        return next((s for s in self.sections if s.title == title), None)

class ReportSchedule(BaseModel):
    """Report scheduling configuration."""
    
    VALID_SCHEDULE_TYPES = ["daily", "weekly", "monthly", "custom"]
    
    report_template_id: PyObjectId
    schedule_type: str
    parameters: Dict[str, Any]
    format: ReportFormat
    recipients: List[str]
    
    next_run: datetime
    last_run: Optional[datetime] = None
    is_active: bool = True
    
    created_by: PyObjectId
    notification_settings: Dict[str, Any] = Field(default_factory=dict)

    @field_validator('schedule_type')
    def validate_schedule_type(cls, v: str) -> str:
        if v not in cls.VALID_SCHEDULE_TYPES:
            raise ValueError(f"Invalid schedule type. Must be one of: {cls.VALID_SCHEDULE_TYPES}")
        return v

    def calculate_next_run(self) -> datetime:
        """Calculate next run time based on schedule type."""
        current = datetime.utcnow()
        
        if self.schedule_type == "daily":
            next_run = current + timedelta(days=1)
        elif self.schedule_type == "weekly":
            next_run = current + timedelta(weeks=1)
        elif self.schedule_type == "monthly":
            if current.month == 12:
                next_run = current.replace(year=current.year + 1, month=1)
            else:
                next_run = current.replace(month=current.month + 1)
        else:
            interval = self.parameters.get("interval", 1)
            unit = self.parameters.get("unit", "days")
            if unit == "hours":
                next_run = current + timedelta(hours=interval)
            elif unit == "days":
                next_run = current + timedelta(days=interval)
            else:
                next_run = current + timedelta(days=1)
        
        return next_run

    def is_due(self) -> bool:
        """Check if schedule is due for execution."""
        return datetime.utcnow() >= self.next_run

    def update_last_run(self) -> None:
        """Update last run time and calculate next run."""
        self.last_run = datetime.utcnow()
        self.next_run = self.calculate_next_run()
        logger.info(f"Schedule updated. Next run: {self.next_run}")

class ReportGeneration(TimestampedModel):
    """Report generation tracking."""
    
    VALID_STATUSES = ["pending", "processing", "completed", "failed", "cancelled"]
    MAX_RETRIES = 3
    
    report_id: str = Field(..., min_length=12)
    template_id: PyObjectId
    generated_by: PyObjectId
    
    parameters: Dict[str, Any]
    output_format: ReportFormat
    generation_status: str = "pending"
    
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration: Optional[float] = None
    
    output_url: Optional[str] = None
    output_size: Optional[int] = None
    
    error_details: Optional[Dict[str, Any]] = None
    retry_count: int = 0

    @field_validator('generation_status')
    def validate_status(cls, v: str) -> str:
        if v not in cls.VALID_STATUSES:
            raise ValueError(f"Invalid status. Must be one of: {cls.VALID_STATUSES}")
        return v

    def handle_error(self, error: Exception) -> None:
        """Handle generation error with retry logic."""
        self.error_details = {
            "error_type": error.__class__.__name__,
            "error_message": str(error),
            "timestamp": datetime.utcnow()
        }
        
        if self.retry_count < self.MAX_RETRIES:
            self.retry_count += 1
            self.generation_status = "pending"
            logger.warning(f"Retrying report generation. Attempt {self.retry_count}/{self.MAX_RETRIES}")
        else:
            self.generation_status = "failed"
            logger.error(f"Report generation failed after {self.MAX_RETRIES} attempts")

    def start_generation(self) -> None:
        """Start report generation process."""
        self.start_time = datetime.utcnow()
        self.generation_status = "processing"
        logger.info(f"Started generation of report {self.report_id}")

    def complete_generation(self, output_url: str, output_size: int) -> None:
        """Complete report generation process."""
        self.end_time = datetime.utcnow()
        self.duration = (self.end_time - self.start_time).total_seconds()
        self.output_url = output_url
        self.output_size = output_size
        self.generation_status = "completed"
        logger.info(f"Completed generation of report {self.report_id}")

class Report(TimestampedModel):
    """Complete report management model."""
    
    VALID_APPROVAL_STATUSES = ["pending", "approved", "rejected"]
    
    report_id: str
    template: ReportTemplate
    generation: ReportGeneration
    
    title: str
    description: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    data_sources: List[Dict[str, Any]]
    parameters: Dict[str, Any]
    
    content_sections: List[Dict[str, Any]] = []
    generated_content: Optional[Dict[str, Any]] = None
    
    approval_status: Optional[str] = None
    approved_by: Optional[PyObjectId] = None
    approval_notes: Optional[str] = None
    
    expiry_date: Optional[datetime] = None
    is_archived: bool = False
    archive_reason: Optional[str] = None

    @field_validator('approval_status')
    def validate_approval_status(cls, v: Optional[str]) -> Optional[str]:
        if v and v not in cls.VALID_APPROVAL_STATUSES:
            raise ValueError(f"Invalid approval status. Must be one of: {cls.VALID_APPROVAL_STATUSES}")
        return v

    def validate_content(self) -> List[str]:
        """Validate report content sections."""
        errors = []
        required_sections = {section.title for section in self.template.sections}
        actual_sections = {section["title"] for section in self.content_sections}
        
        missing = required_sections - actual_sections
        if missing:
            errors.append(f"Missing required sections: {missing}")
            
        return errors

    def validate_expiry(self) -> bool:
        """Check if report has expired."""
        if not self.expiry_date:
            return True
        return datetime.utcnow() < self.expiry_date

    def approve(self, approver_id: PyObjectId, notes: Optional[str] = None) -> None:
        """Approve the report."""
        if self.approval_status == "approved":
            raise ValueError("Report is already approved")
        
        self.approval_status = "approved"
        self.approved_by = approver_id
        self.approval_notes = notes
        self.metadata["approved_at"] = datetime.utcnow()
        logger.info(f"Report {self.report_id} approved by {approver_id}")

    def reject(self, rejector_id: PyObjectId, reason: str) -> None:
        """Reject the report."""
        self.approval_status = "rejected"
        self.approved_by = rejector_id
        self.approval_notes = reason
        self.metadata["rejected_at"] = datetime.utcnow()
        logger.info(f"Report {self.report_id} rejected by {rejector_id}")

    def archive(self, reason: str) -> None:
        """Archive the report."""
        self.is_archived = True
        self.archive_reason = reason
        self.metadata["archived_at"] = datetime.utcnow()
        logger.info(f"Report {self.report_id} archived: {reason}")

    def collect_generation_metrics(self) -> Dict[str, Any]:
        """Collect detailed report generation metrics."""
        return {
            "generation_metrics": {
                "start_time": self.generation.start_time,
                "end_time": self.generation.end_time,
                "duration": self.generation.duration,
                "retries": self.generation.retry_count,
                "status": self.generation.generation_status
            },
            "content_metrics": {
                "sections": len(self.content_sections),
                "total_size": self.generation.output_size,
                "format": self.generation.output_format
            },
            "validation_metrics": {
                "is_approved": self.approval_status == "approved",
                "approval_time": self.metadata.get("approved_at"),
                "is_expired": not self.validate_expiry(),
                "is_archived": self.is_archived
            }
        }

    class Config:
        """Model configuration."""
        validate_assignment = True
        json_encoders = {
            datetime: lambda dt: dt.isoformat(),
            PyObjectId: str
        }