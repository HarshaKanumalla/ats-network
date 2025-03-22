# backend/app/services/test/monitor.py

from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import logging
import asyncio
import json
from bson import ObjectId

from ...core.exceptions import ValidationError, MonitoringError
from ...services.websocket.manager import websocket_manager
from ...services.notification.notification_service import notification_service
from ...database import db_manager
from ...config import get_settings
from .interfaces import TestServiceInterface, TestResultsInterface

logger = logging.getLogger(__name__)
settings = get_settings()

class TestMonitor:
    """Enhanced service for real-time test monitoring and data validation with interface integration."""
    
    def __init__(
        self,
        test_service: TestServiceInterface,
        results_service: TestResultsInterface
    ):
        """Initialize test monitor with services and enhanced validation settings."""
        self.test_service = test_service
        self.results_service = results_service
        self.active_sessions: Dict[str, Dict[str, Any]] = {}
        
        # Enhanced validation thresholds with comprehensive criteria
        self.validation_thresholds = {
            "speed_test": {
                "min_speed": 0,
                "max_speed": 120,
                "min_readings": 10,
                "reading_interval": 0.5,
                "stabilization_time": 5,
                "deviation_threshold": 2.0
            },
            "brake_test": {
                "min_force": 50,
                "max_force": 1000,
                "response_time": 0.75,
                "imbalance_limit": 30,
                "min_deceleration": 5.8
            },
            "headlight_test": {
                "min_intensity": 100,
                "max_intensity": 1000,
                "max_misalignment": 2.0,
                "min_measurements": 5
            },
            "noise_test": {
                "max_level": 85,
                "ambient_threshold": 45,
                "measurement_duration": 10,
                "sample_rate": 10
            }
        }
        
        # Test sequence configurations
        self.test_sequences = {
            "standard": [
                "visual_inspection",
                "brake_test",
                "speed_test",
                "headlight_test",
                "noise_test"
            ],
            "comprehensive": [
                "visual_inspection",
                "brake_test",
                "speed_test",
                "headlight_test",
                "noise_test",
                "axle_test",
                "emission_test"
            ]
        }
        
        # Monitoring settings
        self.session_timeout = timedelta(minutes=30)
        self.data_buffer_size = 1000
        self.alert_threshold = 3
        
        logger.info("Test monitor initialized with enhanced validation settings and service interfaces")

    async def start_monitoring_session(
        self,
        session_id: str,
        vehicle_id: str,
        center_id: str,
        operator_id: str
    ) -> Dict[str, Any]:
        """Initialize and start a new test monitoring session."""
        try:
            # Verify prerequisites
            await self._verify_test_prerequisites(center_id, operator_id)
            
            # Create test session through interface
            session = await self.test_service.create_test_session(
                vehicle_id=vehicle_id,
                center_id=center_id,
                operator_id=operator_id
            )
            
            # Initialize session data
            session_data = {
                **session,
                "session_id": session_id,
                "start_time": datetime.utcnow(),
                "status": "in_progress",
                "current_test": None,
                "completed_tests": [],
                "measurements": {},
                "alerts": [],
                "data_points": 0,
                "metadata": {
                    "client_count": 0,
                    "last_activity": datetime.utcnow()
                }
            }
            
            # Store session data
            await self._store_session_data(session_data)
            
            # Initialize real-time monitoring
            self.active_sessions[session_id] = {
                "data": session_data,
                "monitor_task": asyncio.create_task(
                    self._monitor_session(session_id)
                ),
                "data_buffer": [],
                "alert_count": 0
            }
            
            # Start background tasks
            await self._start_monitoring_tasks(session_id)
            
            # Notify session start
            await self._notify_session_start(session_data)
            
            logger.info(f"Started monitoring session: {session_id}")
            return session_data
            
        except Exception as e:
            logger.error(f"Session start error: {str(e)}")
            raise MonitoringError(f"Failed to start monitoring: {str(e)}")

    async def process_test_data(
        self,
        session_id: str,
        test_type: str,
        raw_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process and validate incoming test data in real-time."""
        try:
            session = self.active_sessions.get(session_id)
            if not session:
                raise MonitoringError("Invalid or expired test session")
            
            # Validate test sequence
            await self._validate_test_sequence(session, test_type)
            
            # Validate test data
            validated_data = await self._validate_test_data(test_type, raw_data)
            
            # Process measurements through test service
            processed_data = await self.test_service.process_measurement(
                session_id=session_id,
                test_type=test_type,
                measurement_data=validated_data
            )
            
            # Update session data
            session["data"]["measurements"].setdefault(test_type, []).append(
                processed_data
            )
            session["data"]["data_points"] += 1
            session["data"]["metadata"]["last_activity"] = datetime.utcnow()
            
            # Buffer data for analysis
            await self._buffer_test_data(session_id, test_type, processed_data)
            
            # Check for anomalies
            if anomalies := await self._check_test_anomalies(
                test_type,
                processed_data,
                session["data_buffer"]
            ):
                await self._handle_anomalies(session_id, anomalies)
            
            # Store results through results service
            await self.results_service.store_test_result(
                session_id=session_id,
                test_type=test_type,
                result_data=processed_data
            )
            
            # Broadcast update
            await websocket_manager.broadcast_test_data(
                session_id,
                test_type,
                processed_data
            )
            
            return processed_data
            
        except Exception as e:
            logger.error(f"Data processing error: {str(e)}")
            raise MonitoringError(f"Failed to process test data: {str(e)}")

    async def _validate_test_sequence(
        self,
        session: Dict[str, Any],
        test_type: str
    ) -> None:
        """Validate test execution sequence."""
        current_test = session["data"]["current_test"]
        completed_tests = session["data"]["completed_tests"]
        
        if current_test and current_test != test_type:
            raise ValidationError(
                f"Invalid test sequence. Expected: {current_test}, Got: {test_type}"
            )
        
        if test_type in completed_tests:
            raise ValidationError(f"Test {test_type} already completed")

    async def _validate_test_data(
        self,
        test_type: str,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate test data against defined thresholds."""
        thresholds = self.validation_thresholds.get(test_type)
        if not thresholds:
            raise ValidationError(f"Invalid test type: {test_type}")
            
        validated_data = {}
        
        if test_type == "speed_test":
            speed = float(data.get("speed", 0))
            if not (thresholds["min_speed"] <= speed <= thresholds["max_speed"]):
                raise ValidationError(
                    f"Speed {speed} outside valid range "
                    f"[{thresholds['min_speed']}, {thresholds['max_speed']}]"
                )
            validated_data["speed"] = speed
            validated_data["timestamp"] = datetime.utcnow()
            
        elif test_type == "brake_test":
            force = float(data.get("force", 0))
            if not (thresholds["min_force"] <= force <= thresholds["max_force"]):
                raise ValidationError(
                    f"Brake force {force} outside valid range "
                    f"[{thresholds['min_force']}, {thresholds['max_force']}]"
                )
            validated_data["force"] = force
            validated_data["response_time"] = float(data.get("response_time", 0))
            validated_data["timestamp"] = datetime.utcnow()
            
        # Add validation for other test types...
        
        return validated_data

    async def _buffer_test_data(
        self,
        session_id: str,
        test_type: str,
        data: Dict[str, Any]
    ) -> None:
        """Buffer test data for analysis."""
        buffer = self.active_sessions[session_id]["data_buffer"]
        buffer.append({
            "test_type": test_type,
            "data": data,
            "timestamp": datetime.utcnow()
        })
        
        # Maintain buffer size
        if len(buffer) > self.data_buffer_size:
            buffer.pop(0)

    async def _check_test_anomalies(
        self,
        test_type: str,
        current_data: Dict[str, Any],
        data_buffer: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Check for anomalies in test data."""
        anomalies = []
        thresholds = self.validation_thresholds[test_type]
        
        if test_type == "speed_test":
            # Check speed stability
            recent_speeds = [
                d["data"]["speed"] for d in data_buffer[-5:]
                if d["test_type"] == "speed_test"
            ]
            if recent_speeds:
                avg_speed = sum(recent_speeds) / len(recent_speeds)
                if abs(current_data["speed"] - avg_speed) > thresholds["deviation_threshold"]:
                    anomalies.append({
                        "type": "speed_instability",
                        "value": current_data["speed"],
                        "average": avg_speed,
                        "threshold": thresholds["deviation_threshold"]
                    })
                    
        # Add anomaly detection for other test types...
        
        return anomalies

    async def _handle_anomalies(
        self,
        session_id: str,
        anomalies: List[Dict[str, Any]]
    ) -> None:
        """Handle detected test anomalies."""
        session = self.active_sessions[session_id]
        session["alert_count"] += len(anomalies)
        
        for anomaly in anomalies:
            # Add to session alerts
            session["data"]["alerts"].append({
                "type": anomaly["type"],
                "details": anomaly,
                "timestamp": datetime.utcnow()
            })
            
            # Store anomaly through results service
            await self.results_service.store_test_anomaly(
                session_id=session_id,
                anomaly_data=anomaly
            )
            
            # Notify operator
            await notification_service.send_notification(
                user_id=str(session["data"]["operator_id"]),
                title="Test Anomaly Detected",
                message=f"Anomaly detected: {anomaly['type']}",
                data=anomaly
            )
            
            # Check alert threshold
            if session["alert_count"] >= self.alert_threshold:
                await self._handle_critical_alerts(session_id)

    async def _verify_test_prerequisites(
        self,
        center_id: str,
        operator_id: str
    ) -> None:
        """Verify all prerequisites for test session."""
        try:
            # Verify center and operator through test service
            await self.test_service.verify_test_prerequisites(
                center_id=center_id,
                operator_id=operator_id
            )
            
        except Exception as e:
            logger.error(f"Prerequisites verification error: {str(e)}")
            raise MonitoringError(f"Failed to verify prerequisites: {str(e)}")

    async def _monitor_session(self, session_id: str) -> None:
        """Monitor test session for timeouts and anomalies."""
        try:
            while session_id in self.active_sessions:
                session = self.active_sessions[session_id]
                current_time = datetime.utcnow()
                
                # Check session timeout
                last_activity = session["data"]["metadata"]["last_activity"]
                if current_time - last_activity > self.session_timeout:
                    await self._handle_session_timeout(session_id)
                    break
                
                # Check data consistency
                await self._check_data_consistency(session_id)
                
                # Monitor equipment status through test service
                await self.test_service.check_equipment_status(
                    center_id=str(session["data"]["center_id"])
                )
                
                await asyncio.sleep(5)  # Check every 5 seconds
                
        except Exception as e:
            logger.error(f"Session monitoring error: {str(e)}")
            await self._handle_session_error(session_id, str(e))

# Initialize test monitor
test_monitor = TestMonitor()