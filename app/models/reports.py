#backend/app/models/reports.py

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, validator
from enum import Enum

from .common import TimestampedModel, PyObjectId
from ..core.constants import UserRole

class ReportType(str, Enum):
    """Report type definitions."""
    TEST_REPORT = "test_report"
    CENTER_PERFORMANCE = "center_performance"
    VEHICLE_HISTORY = "vehicle_history"
    SYSTEM_ANALYTICS = "system_analytics"
    COMPLIANCE_REPORT = "compliance_report"
    AUDIT_REPORT = "audit_report"

class ReportFormat(str, Enum):
    """Report output format options."""
    PDF = "pdf"
    EXCEL = "excel"
    HTML = "html"
    JSON = "json"

class ReportSection(BaseModel):
    """Individual report section definition."""
    
    title: str
    section_type: str
    content_template: str
    data_source: str
    parameters: Dict[str, Any]
    required_permissions: List[str] = []
    validation_rules: Optional[Dict[str, Any]] = None
    display_order: int

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

class ReportSchedule(BaseModel):
    """Report scheduling configuration."""
    
    report_template_id: PyObjectId
    schedule_type: str  # daily, weekly, monthly
    parameters: Dict[str, Any]
    format: ReportFormat
    recipients: List[str]
    
    next_run: datetime
    last_run: Optional[datetime] = None
    is_active: bool = True
    
    created_by: PyObjectId
    notification_settings: Dict[str, Any] = Field(default_factory=dict)

class ReportGeneration(TimestampedModel):
    """Report generation tracking."""
    
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
    
    @validator('report_id')
    def validate_report_id(cls, v: str) -> str:
        """Validate report ID format."""
        if not v.startswith('RPT'):
            raise ValueError("Report ID must start with 'RPT'")
        return v

class Report(TimestampedModel):
    """Complete report management model."""
    
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
    
    class Config:
        """Model configuration."""
        validate_assignment = True
        json_encoders = {
            datetime: lambda dt: dt.isoformat(),
            PyObjectId: str
        }

    def update_generation_status(
        self,
        status: str,
        error: Optional[Dict[str, Any]] = None
    ) -> None:
        """Update report generation status."""
        self.generation.generation_status = status
        if status == "completed":
            self.generation.end_time = datetime.utcnow()
            if self.generation.start_time:
                self.generation.duration = (
                    self.generation.end_time - self.generation.start_time
                ).total_seconds()
        elif status == "failed" and error:
            self.generation.error_details = error

    def add_content_section(
        self,
        section_title: str,
        content: Dict[str, Any]
    ) -> None:
        """Add content section to report."""
        self.content_sections.append({
            "title": section_title,
            "content": content,
            "added_at": datetime.utcnow()
        })

    def approve_report(
        self,
        approved_by: PyObjectId,
        notes: Optional[str] = None
    ) -> None:
        """Approve generated report."""
        self.approval_status = "approved"
        self.approved_by = approved_by
        self.approval_notes = notes
        self.metadata["approved_at"] = datetime.utcnow()

    def archive_report(
        self,
        reason: str,
        archived_by: PyObjectId
    ) -> None:
        """Archive report with tracking."""
        self.is_archived = True
        self.archive_reason = reason
        self.metadata["archived_at"] = datetime.utcnow()
        self.metadata["archived_by"] = archived_by

    def get_section_content(
        self,
        section_title: str
    ) -> Optional[Dict[str, Any]]:
        """Get content of specific report section."""
        for section in self.content_sections:
            if section["title"] == section_title:
                return section["content"]
        return None

    def validate_expiry(self) -> bool:
        """Check if report has expired."""
        if not self.expiry_date:
            return True
        return datetime.utcnow() < self.expiry_date

    def calculate_metrics(self) -> Dict[str, Any]:
        """Calculate report generation metrics."""
        return {
            "generation_time": self.generation.duration,
            "size": self.generation.output_size,
            "sections_count": len(self.content_sections),
            "retry_count": self.generation.retry_count,
            "has_approval": self.approval_status is not None
        }