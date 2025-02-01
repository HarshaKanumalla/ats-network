#backend/app/models/test.py

"""Test session and result data models."""
from typing import Optional, List, Dict, Any
from pydantic import Field
from datetime import datetime

from .common import AuditedModel, PyObjectId

class TestBase(AuditedModel):
    """Base model for test data."""
    
    session_code: str = Field(
        ..., 
        pattern=r'^TS\d{12}$',
        description="Unique test session code"
    )
    center_id: PyObjectId = Field(..., description="ATS center ID")
    vehicle_id: PyObjectId = Field(..., description="Vehicle ID")
    
    # Test status
    status: str = Field(default="scheduled")
    scheduled_time: datetime = Field(default_factory=datetime.utcnow)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    # Staff involved
    tested_by: Optional[PyObjectId] = None
    reviewed_by: Optional[PyObjectId] = None
    approved_by: Optional[PyObjectId] = None

class VisualInspectionResult(AuditedModel):
    """Visual inspection test results."""
    
    number_plate: Dict[str, Any] = Field(default_factory=lambda: {
        "status": "pending",
        "image_url": None,
        "notes": None
    })
    
    reflective_tape: Dict[str, Any] = Field(default_factory=lambda: {
        "status": "pending",
        "image_url": None,
        "notes": None
    })
    
    side_mirrors: Dict[str, Any] = Field(default_factory=lambda: {
        "status": "pending",
        "image_url": None,
        "notes": None
    })
    
    additional_images: List[Dict[str, Any]] = Field(default_factory=list)
    
    overall_status: str = Field(default="pending")
    inspector_notes: Optional[str] = None

class SpeedTestResult(AuditedModel):
    """Speed test results."""
    
    max_speed: float = Field(..., ge=0)
    target_speed: float = Field(default=60.0)
    actual_speed: float = Field(..., ge=0)
    deviation: float = Field(..., description="Speed deviation percentage")
    test_duration: float = Field(..., ge=0)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    status: str = Field(default="pending")
    notes: Optional[str] = None

class BrakeTestResult(AuditedModel):
    """Brake test results."""
    
    brake_force: float = Field(..., ge=0)
    imbalance_final: float = Field(..., ge=0)
    imbalance_max: float = Field(..., ge=0)
    deceleration_static: float = Field(..., ge=0)
    deceleration_dynamic: float = Field(..., ge=0)
    test_duration: float = Field(..., ge=0)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    status: str = Field(default="pending")
    notes: Optional[str] = None

class NoiseTestResult(AuditedModel):
    """Noise test results."""
    
    readings: List[Dict[str, float]] = Field(default_factory=list)
    average_value: float = Field(..., ge=0)
    max_value: float = Field(..., ge=0)
    test_duration: float = Field(..., ge=0)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    status: str = Field(default="pending")
    notes: Optional[str] = None

class HeadlightTestResult(AuditedModel):
    """Headlight test results."""
    
    pitch_angle: float = Field(..., description="Vertical alignment angle")
    yaw_angle: float = Field(..., description="Horizontal alignment angle")
    roll_angle: float = Field(..., description="Rotational alignment angle")
    intensity: float = Field(..., ge=0, description="Light intensity")
    glare: float = Field(..., ge=0, description="Glare measurement")
    test_duration: float = Field(..., ge=0)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    status: str = Field(default="pending")
    notes: Optional[str] = None

class AxleTestResult(AuditedModel):
    """Axle weight test results."""
    
    readings: List[Dict[str, Any]] = Field(default_factory=list)
    total_weight: float = Field(..., ge=0)
    weight_distribution: Dict[str, float] = Field(default_factory=dict)
    test_duration: float = Field(..., ge=0)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    status: str = Field(default="pending")
    notes: Optional[str] = None

class AccelerationTestResult(AuditedModel):
    """Acceleration test results."""
    
    acceleration: float = Field(..., ge=0)
    time_elapsed: float = Field(..., ge=0)
    distance_covered: float = Field(..., ge=0)
    test_duration: float = Field(..., ge=0)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    status: str = Field(default="pending")
    notes: Optional[str] = None

class TestSession(TestBase):
    """Complete test session model."""
    
    # Test results
    visual_inspection: Optional[VisualInspectionResult] = None
    speed_test: Optional[SpeedTestResult] = None
    brake_test: Optional[BrakeTestResult] = None
    noise_test: Optional[NoiseTestResult] = None
    headlight_test: Optional[HeadlightTestResult] = None
    axle_test: Optional[AxleTestResult] = None
    acceleration_test: Optional[AccelerationTestResult] = None
    
    # Final results
    overall_status: str = Field(default="pending")
    completion_percentage: float = Field(default=0.0)
    test_duration: Optional[float] = None
    issues_found: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    
    # Certificate details
    certificate_number: Optional[str] = None
    certificate_url: Optional[str] = None
    valid_until: Optional[datetime] = None
    
    class Config:
        json_encoders = {
            datetime: lambda dt: dt.isoformat() if dt else None,
            PyObjectId: str
        }

class TestReport(AuditedModel):
    """Test report generation model."""
    
    session_id: PyObjectId
    report_number: str = Field(..., pattern=r'^RPT\d{12}$')
    report_url: str = Field(...)
    
    # Report details
    test_summary: Dict[str, Any] = Field(...)
    detailed_results: Dict[str, Any] = Field(...)
    recommendations: List[str] = Field(default_factory=list)
    
    # Approval details
    approval_status: str = Field(default="pending")
    approved_by: Optional[PyObjectId] = None
    approved_at: Optional[datetime] = None
    approval_notes: Optional[str] = None
    
    class Config:
        json_encoders = {
            datetime: lambda dt: dt.isoformat() if dt else None,
            PyObjectId: str
        }
