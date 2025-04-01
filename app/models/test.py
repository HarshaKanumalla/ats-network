from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, validator, field_validator
from enum import Enum
import logging

from .common import TimestampedModel, PyObjectId
from ..core.constants import TestStatus, TestType

logger = logging.getLogger(__name__)

class TestStep(BaseModel):
    """Individual test step in a test procedure."""
    
    VALID_COMPLETION_CRITERIA = ["value_threshold", "time_based", "visual_inspection", "operator_confirmation"]
    
    step_number: int
    description: str
    required_equipment: List[str]
    parameters: Dict[str, Any]
    validation_rules: Dict[str, Any]
    completion_criteria: Dict[str, Any]
    estimated_duration: int  # in seconds
    instructions: str

    @field_validator('step_number')
    def validate_step_number(cls, v: int) -> int:
        if v < 1:
            raise ValueError("Step number must be positive")
        return v

    @field_validator('estimated_duration')
    def validate_duration(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Duration must be positive")
        return v

    def validate_completion_criteria(self) -> List[str]:
        """Validate completion criteria configuration."""
        errors = []
        if not self.completion_criteria:
            errors.append("Completion criteria cannot be empty")
        else:
            criteria_type = self.completion_criteria.get("type")
            if criteria_type not in self.VALID_COMPLETION_CRITERIA:
                errors.append(f"Invalid completion criteria type: {criteria_type}")
            
            # Validate criteria specific requirements
            if criteria_type == "value_threshold":
                if "threshold" not in self.completion_criteria:
                    errors.append("Missing threshold value")
            elif criteria_type == "time_based":
                if "duration" not in self.completion_criteria:
                    errors.append("Missing duration value")
        return errors

class TestMeasurement(BaseModel):
    """Test measurement data with validation."""
    
    VALID_STATUSES = ["pending", "valid", "invalid", "requires_review"]
    
    parameter: str
    value: float
    unit: str
    timestamp: datetime
    equipment_id: str
    operator_id: PyObjectId
    validation_status: str = "pending"
    validation_notes: Optional[str] = None

    @field_validator('value')
    def validate_value(cls, v: float) -> float:
        if not isinstance(v, (int, float)):
            raise ValueError("Value must be numeric")
        return float(v)

    @field_validator('validation_status')
    def validate_status(cls, v: str) -> str:
        if v not in cls.VALID_STATUSES:
            raise ValueError(f"Invalid status. Must be one of: {cls.VALID_STATUSES}")
        return v

    def is_within_range(self, min_value: float, max_value: float) -> bool:
        """Check if measurement is within specified range."""
        return min_value <= self.value <= max_value

class QualityCheck(BaseModel):
    """Quality control check for test results."""
    
    check_type: str
    threshold: float
    actual_value: float
    status: str
    verified_by: Optional[PyObjectId] = None
    verification_time: Optional[datetime] = None
    notes: Optional[str] = None

    def evaluate(self) -> bool:
        """Evaluate quality check result."""
        if self.check_type == "maximum":
            return self.actual_value <= self.threshold
        elif self.check_type == "minimum":
            return self.actual_value >= self.threshold
        elif self.check_type == "exact":
            return abs(self.actual_value - self.threshold) < 0.001
        return False

class TestVerification(BaseModel):
    """Test result verification details."""
    
    verifier_id: PyObjectId
    verification_time: datetime
    status: str
    comments: Optional[str] = None
    quality_checks: List[QualityCheck]
    supporting_documents: Optional[List[str]] = None

    def all_checks_passed(self) -> bool:
        """Check if all quality checks passed."""
        return all(check.evaluate() for check in self.quality_checks)

class TestProcedure(BaseModel):
    """Complete test procedure definition."""
    
    test_type: TestType
    version: str
    steps: List[TestStep]
    required_equipment: List[str]
    safety_requirements: List[str]
    prerequisites: List[str]
    total_duration: int  # in seconds

    def validate_steps_sequence(self) -> List[str]:
        """Validate test steps sequence."""
        errors = []
        step_numbers = [step.step_number for step in self.steps]
        if len(step_numbers) != len(set(step_numbers)):
            errors.append("Duplicate step numbers found")
        if step_numbers != sorted(step_numbers):
            errors.append("Steps are not in sequential order")
        return errors

class TestSession(TimestampedModel):
    """Enhanced test session with comprehensive tracking."""
    
    VALID_TRANSITIONS = {
        TestStatus.SCHEDULED: [TestStatus.IN_PROGRESS, TestStatus.CANCELLED],
        TestStatus.IN_PROGRESS: [TestStatus.COMPLETED, TestStatus.INTERRUPTED],
        TestStatus.INTERRUPTED: [TestStatus.IN_PROGRESS, TestStatus.CANCELLED],
        TestStatus.COMPLETED: [TestStatus.VERIFIED, TestStatus.REJECTED],
        TestStatus.VERIFIED: [],
        TestStatus.REJECTED: [],
        TestStatus.CANCELLED: []
    }
    
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

    def update_status(self, new_status: TestStatus) -> None:
        """Update test status with validation."""
        if new_status not in self.VALID_TRANSITIONS[self.status]:
            raise ValueError(
                f"Invalid status transition from {self.status} to {new_status}"
            )
        self.status = new_status
        logger.info(f"Test session {self.session_code} status updated to {new_status}")

    def start_test(self) -> None:
        """Start test session."""
        if self.status != TestStatus.SCHEDULED:
            raise ValueError(f"Cannot start test in {self.status} status")
        self.start_time = datetime.utcnow()
        self.update_status(TestStatus.IN_PROGRESS)
        logger.info(f"Test session {self.session_code} started")

    def end_test(self) -> None:
        """End test session."""
        if self.status != TestStatus.IN_PROGRESS:
            raise ValueError(f"Cannot end test in {self.status} status")
        self.end_time = datetime.utcnow()
        self.duration = int((self.end_time - self.start_time).total_seconds())
        self.update_status(TestStatus.COMPLETED)
        logger.info(f"Test session {self.session_code} completed")

    def validate_equipment(self) -> List[str]:
        """Validate required equipment availability."""
        errors = []
        for equipment in self.test_procedure.required_equipment:
            if equipment not in self.equipment_used:
                errors.append(f"Missing required equipment: {equipment}")
        return errors

    def add_issue(self, issue: Dict[str, Any]) -> None:
        """Record test issue."""
        issue["timestamp"] = datetime.utcnow()
        self.issues_detected.append(issue)
        logger.warning(f"Issue detected in session {self.session_code}: {issue['description']}")

    class Config:
        """Model configuration."""
        validate_assignment = True
        json_encoders = {
            datetime: lambda dt: dt.isoformat(),
            PyObjectId: str
        }

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
    
    @field_validator('pass_fail_status')
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

    def analyze_trends(self) -> Dict[str, Any]:
        """Analyze measurement trends."""
        trends = {
            "increasing": False,
            "decreasing": False,
            "stable": False,
            "fluctuating": False
        }
        
        if len(self.measurements) < 2:
            return trends
        
        values = [m.value for m in self.measurements]
        diffs = [values[i+1] - values[i] for i in range(len(values)-1)]
        
        avg_diff = sum(diffs) / len(diffs)
        std_dev = (sum((d - avg_diff) ** 2 for d in diffs) / len(diffs)) ** 0.5
        
        if abs(avg_diff) < 0.1 * std_dev:
            trends["stable"] = True
        elif avg_diff > 0:
            trends["increasing"] = True
        else:
            trends["decreasing"] = True
            
        if std_dev > abs(avg_diff) * 2:
            trends["fluctuating"] = True
            
        return trends