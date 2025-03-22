#backend/app/models/test.py

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, validator
from enum import Enum

from .common import TimestampedModel, PyObjectId
from ..core.constants import TestStatus, TestType

class TestStep(BaseModel):
    """Individual test step in a test procedure."""
    
    step_number: int
    description: str
    required_equipment: List[str]
    parameters: Dict[str, Any]
    validation_rules: Dict[str, Any]
    completion_criteria: Dict[str, Any]
    estimated_duration: int  # in seconds
    instructions: str

class TestMeasurement(BaseModel):
    """Test measurement data with validation."""
    
    parameter: str
    value: float
    unit: str
    timestamp: datetime
    equipment_id: str
    operator_id: PyObjectId
    validation_status: str = "pending"
    validation_notes: Optional[str] = None

class QualityCheck(BaseModel):
    """Quality control check for test results."""
    
    check_type: str
    threshold: float
    actual_value: float
    status: str
    verified_by: Optional[PyObjectId] = None
    verification_time: Optional[datetime] = None
    notes: Optional[str] = None

class TestVerification(BaseModel):
    """Test result verification details."""
    
    verifier_id: PyObjectId
    verification_time: datetime
    status: str
    comments: Optional[str] = None
    quality_checks: List[QualityCheck]
    supporting_documents: Optional[List[str]] = None

class TestProcedure(BaseModel):
    """Complete test procedure definition."""
    
    test_type: TestType
    version: str
    steps: List[TestStep]
    required_equipment: List[str]
    safety_requirements: List[str]
    prerequisites: List[str]
    total_duration: int  # in seconds

class TestSession(TimestampedModel):
    """Enhanced test session with comprehensive tracking."""
    
    session_code: str = Field(..., regex=r'^TS\d{12}$')
    vehicle_id: PyObjectId
    center_id: PyObjectId
    operator_id: PyObjectId
    supervisor_id: Optional[PyObjectId] = None
    
    test_procedure: TestProcedure
    current_step: int = 0
    status: TestStatus = TestStatus.SCHEDULED
    
    scheduled_time: datetime
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration: Optional[int] = None
    
    measurements: Dict[str, List[TestMeasurement]] = {}
    quality_checks: List[QualityCheck] = []
    verifications: List[TestVerification] = []
    
    environmental_conditions: Dict[str, Any] = {}
    equipment_used: Dict[str, str] = {}
    
    interruptions: List[Dict[str, Any]] = []
    issues_detected: List[Dict[str, Any]] = []
    
    final_results: Dict[str, Any] = Field(default_factory=dict)
    verification_status: str = "pending"
    certificate_number: Optional[str] = None
    
    class Config:
        """Model configuration."""
        validate_assignment = True
        json_encoders = {
            datetime: lambda dt: dt.isoformat(),
            PyObjectId: str
        }

    @validator('session_code')
    def validate_session_code(cls, v: str) -> str:
        """Validate test session code format."""
        if not v.startswith('TS') or not len(v) == 14:
            raise ValueError("Invalid session code format")
        return v

    def add_measurement(
        self,
        test_type: str,
        measurement: TestMeasurement
    ) -> None:
        """Add new measurement with validation."""
        if test_type not in self.measurements:
            self.measurements[test_type] = []
        self.measurements[test_type].append(measurement)

    def record_interruption(
        self,
        reason: str,
        duration: int,
        reported_by: PyObjectId
    ) -> None:
        """Record test interruption."""
        self.interruptions.append({
            "reason": reason,
            "duration": duration,
            "reported_by": reported_by,
            "timestamp": datetime.utcnow()
        })

    def add_quality_check(self, check: QualityCheck) -> None:
        """Add quality control check result."""
        self.quality_checks.append(check)

    def verify_results(
        self,
        verification: TestVerification
    ) -> None:
        """Add test result verification."""
        self.verifications.append(verification)
        if all(check.status == "passed" for check in verification.quality_checks):
            self.verification_status = "verified"
        else:
            self.verification_status = "failed"

    def complete_step(
        self,
        step_number: int,
        completed_by: PyObjectId
    ) -> None:
        """Mark test step as completed."""
        if step_number != self.current_step:
            raise ValueError("Invalid step number")
            
        self.current_step += 1
        if self.current_step >= len(self.test_procedure.steps):
            self.status = TestStatus.COMPLETED

    def calculate_results(self) -> Dict[str, Any]:
        """Calculate final test results."""
        results = {}
        for test_type, measurements in self.measurements.items():
            values = [m.value for m in measurements]
            results[test_type] = {
                "average": sum(values) / len(values),
                "max": max(values),
                "min": min(values),
                "count": len(values),
                "unit": measurements[0].unit
            }
        self.final_results = results
        return results

class TestResult(BaseModel):
    """Test result with detailed analysis."""
    
    session_id: PyObjectId
    test_type: TestType
    measurements: List[TestMeasurement]
    quality_checks: List[QualityCheck]
    verification: TestVerification
    result_summary: Dict[str, Any]
    pass_fail_status: str
    recommendations: Optional[List[str]] = None
    
    @validator('pass_fail_status')
    def validate_status(cls, v: str) -> str:
        """Validate pass/fail status."""
        if v not in ['pass', 'fail']:
            raise ValueError("Status must be 'pass' or 'fail'")
        return v

    def generate_summary(self) -> Dict[str, Any]:
        """Generate test result summary."""
        return {
            "test_type": self.test_type,
            "status": self.pass_fail_status,
            "measurement_count": len(self.measurements),
            "quality_status": all(qc.status == "passed" for qc in self.quality_checks),
            "verification_status": self.verification.status,
            "completion_time": self.verification.verification_time
        }