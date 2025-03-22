# backend/app/services/test/interfaces.py

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from datetime import datetime

class TestMonitorInterface(ABC):
    @abstractmethod
    async def start_monitoring_session(
        self,
        session_id: str,
        vehicle_id: str,
        center_id: str,
        operator_id: str
    ) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    async def process_test_data(
        self,
        session_id: str,
        test_type: str,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        pass

class TestServiceInterface(ABC):
    @abstractmethod
    async def create_test_session(
        self,
        vehicle_id: str,
        center_id: str,
        operator_id: str
    ) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    async def update_test_data(
        self,
        session_id: str,
        test_type: str,
        data: Dict[str, Any],
        updated_by: str
    ) -> Dict[str, Any]:
        pass

class TestResultsInterface(ABC):
    @abstractmethod
    async def process_test_results(
        self,
        session_id: str,
        test_data: Dict[str, Any],
        operator_id: str
    ) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    async def generate_test_report(
        self,
        session_id: str
    ) -> str:
        pass