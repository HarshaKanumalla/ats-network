from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum

class TestStatus(Enum):
    """Test session status enumeration."""
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PENDING_REVIEW = "pending_review"

class TestMonitorInterface(ABC):
    """Interface for monitoring test sessions and equipment."""

    @abstractmethod
    async def start_monitoring_session(
        self,
        session_id: str,
        vehicle_id: str,
        center_id: str,
        operator_id: str
    ) -> Dict[str, Any]:
        """
        Start monitoring a test session.

        Args:
            session_id: Unique test session identifier
            vehicle_id: Vehicle being tested
            center_id: Testing center ID
            operator_id: Test operator ID

        Returns:
            Dict containing monitoring session details
        """
        pass
    
    @abstractmethod
    async def process_test_data(
        self,
        session_id: str,
        test_type: str,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process incoming test data stream."""
        pass

    @abstractmethod
    async def check_equipment_status(
        self,
        center_id: str,
        equipment_ids: List[str]
    ) -> Dict[str, Any]:
        """Check testing equipment status."""
        pass

    @abstractmethod
    async def handle_monitoring_error(
        self,
        session_id: str,
        error_type: str,
        error_data: Dict[str, Any]
    ) -> None:
        """Handle monitoring system errors."""
        pass

class TestServiceInterface(ABC):
    """Interface for managing test sessions and operations."""

    @abstractmethod
    async def create_test_session(
        self,
        vehicle_id: str,
        center_id: str,
        operator_id: str,
        test_types: List[str],
        scheduled_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Create a new test session."""
        pass
    
    @abstractmethod
    async def update_test_data(
        self,
        session_id: str,
        test_type: str,
        data: Dict[str, Any],
        updated_by: str
    ) -> Dict[str, Any]:
        """Update test session data."""
        pass

    @abstractmethod
    async def validate_test_requirements(
        self,
        vehicle_id: str,
        test_types: List[str]
    ) -> Dict[str, bool]:
        """Validate vehicle test requirements."""
        pass

    @abstractmethod
    async def update_session_status(
        self,
        session_id: str,
        status: TestStatus,
        updated_by: str,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update test session status."""
        pass

    @abstractmethod
    async def cancel_test_session(
        self,
        session_id: str,
        reason: str,
        cancelled_by: str
    ) -> None:
        """Cancel an active test session."""
        pass

class TestResultsInterface(ABC):
    """Interface for processing and managing test results."""

    @abstractmethod
    async def process_test_results(
        self,
        session_id: str,
        test_data: Dict[str, Any],
        operator_id: str
    ) -> Dict[str, Any]:
        """Process test session results."""
        pass
    
    @abstractmethod
    async def generate_test_report(
        self,
        session_id: str,
        report_type: str = "detailed"
    ) -> str:
        """Generate test session report."""
        pass

    @abstractmethod
    async def validate_test_results(
        self,
        session_id: str,
        test_type: str
    ) -> Dict[str, Any]:
        """Validate test results against standards."""
        pass

    @abstractmethod
    async def store_test_results(
        self,
        session_id: str,
        results: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Store processed test results."""
        pass

    @abstractmethod
    async def get_test_history(
        self,
        vehicle_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """Retrieve vehicle test history."""
        pass