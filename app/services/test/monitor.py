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
from .interfaces import TestServiceInterface, TestResultsInterface, TestStatus

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
        
        logger.info("Test monitor initialized with enhanced validation settings")

    async def start_monitoring_session(
        self,
        session_id: str,
        vehicle_id: str,
        center_id: str,
        operator_id: str
    ) -> Dict[str, Any]:
        """Initialize and start a new test monitoring session."""
        try:
            await self._verify_test_prerequisites(center_id, operator_id)
            
            session = await self.test_service.create_test_session(
                vehicle_id=vehicle_id,
                center_id=center_id,
                operator_id=operator_id
            )
            
            session_data = {
                **session,
                "session_id": session_id,
                "start_time": datetime.utcnow(),
                "status": TestStatus.IN_PROGRESS.value,
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
            
            await self._store_session_data(session_data)
            
            self.active_sessions[session_id] = {
                "data": session_data,
                "monitor_task": asyncio.create_task(self._monitor_session(session_id)),
                "data_buffer": [],
                "alert_count": 0
            }
            
            await self._start_monitoring_tasks(session_id)
            await self._notify_session_start(session_data)
            
            logger.info(f"Started monitoring session: {session_id}")
            return session_data
            
        except Exception as e:
            logger.error(f"Session start error: {str(e)}")
            raise MonitoringError(f"Failed to start monitoring: {str(e)}")

    async def _start_monitoring_tasks(self, session_id: str) -> None:
        """Start background monitoring tasks for the session."""
        try:
            session = self.active_sessions[session_id]
            
            # Start data consistency check task
            session["consistency_task"] = asyncio.create_task(
                self._check_data_consistency(session_id)
            )
            
            # Start equipment monitoring task
            session["equipment_task"] = asyncio.create_task(
                self._monitor_equipment(session_id)
            )
            
            logger.info(f"Started monitoring tasks for session: {session_id}")
            
        except Exception as e:
            logger.error(f"Failed to start monitoring tasks: {str(e)}")
            raise MonitoringError(f"Failed to initialize monitoring tasks: {str(e)}")

    async def _notify_session_start(self, session_data: Dict[str, Any]) -> None:
        """Notify relevant parties about session start."""
        try:
            # Notify operator
            await notification_service.send_notification(
                user_id=str(session_data["operator_id"]),
                title="Test Session Started",
                message=f"Test session {session_data['session_id']} has started",
                notification_type="session_start",
                data={"session_id": session_data["session_id"]}
            )
            
            # Broadcast session start
            await websocket_manager.broadcast_session_event(
                session_data["session_id"],
                "session_started",
                session_data
            )
            
        except Exception as e:
            logger.error(f"Session start notification error: {str(e)}")

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
            
            await self._validate_test_sequence(session, test_type)
            validated_data = await self._validate_test_data(test_type, raw_data)
            
            processed_data = await self.test_service.process_measurement(
                session_id=session_id,
                test_type=test_type,
                measurement_data=validated_data
            )
            
            session["data"]["measurements"].setdefault(test_type, []).append(processed_data)
            session["data"]["data_points"] += 1
            session["data"]["metadata"]["last_activity"] = datetime.utcnow()
            
            await self._buffer_test_data(session_id, test_type, processed_data)
            
            if anomalies := await self._check_test_anomalies(
                test_type,
                processed_data,
                session["data_buffer"]
            ):
                await self._handle_anomalies(session_id, anomalies)
            
            await self.results_service.store_test_result(
                session_id=session_id,
                test_type=test_type,
                result_data=processed_data
            )
            
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
            
        validated_data = {
            "timestamp": datetime.utcnow()
        }
        
        try:
            if test_type == "speed_test":
                speed = float(data.get("speed", 0))
                if not (thresholds["min_speed"] <= speed <= thresholds["max_speed"]):
                    raise ValidationError(f"Speed {speed} outside valid range")
                validated_data["speed"] = speed
                
            elif test_type == "brake_test":
                force = float(data.get("force", 0))
                if not (thresholds["min_force"] <= force <= thresholds["max_force"]):
                    raise ValidationError(f"Brake force {force} outside valid range")
                validated_data["force"] = force
                validated_data["response_time"] = float(data.get("response_time", 0))
                
            elif test_type == "headlight_test":
                intensity = float(data.get("intensity", 0))
                misalignment = float(data.get("misalignment", 0))
                
                if not (thresholds["min_intensity"] <= intensity <= thresholds["max_intensity"]):
                    raise ValidationError(f"Light intensity {intensity} outside valid range")
                    
                if misalignment > thresholds["max_misalignment"]:
                    raise ValidationError(f"Misalignment {misalignment} exceeds maximum")
                    
                validated_data.update({
                    "intensity": intensity,
                    "misalignment": misalignment
                })
                
            elif test_type == "noise_test":
                noise_level = float(data.get("noise_level", 0))
                ambient_level = float(data.get("ambient_level", 0))
                
                if ambient_level > thresholds["ambient_threshold"]:
                    raise ValidationError(f"Ambient noise too high: {ambient_level}")
                    
                if noise_level > thresholds["max_level"]:
                    raise ValidationError(f"Noise level {noise_level} exceeds maximum")
                    
                validated_data.update({
                    "noise_level": noise_level,
                    "ambient_level": ambient_level
                })
            
            return validated_data
            
        except ValueError as e:
            raise ValidationError(f"Invalid data format: {str(e)}")

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
        
        elif test_type == "brake_test":
            response_time = current_data.get("response_time", 0)
            if response_time > thresholds["response_time"]:
                anomalies.append({
                    "type": "slow_brake_response",
                    "value": response_time,
                    "threshold": thresholds["response_time"]
                })
                
        elif test_type == "headlight_test":
            intensity = current_data.get("intensity", 0)
            recent_intensities = [
                d["data"]["intensity"] for d in data_buffer[-3:]
                if d["test_type"] == "headlight_test"
            ]
            if recent_intensities:
                avg_intensity = sum(recent_intensities) / len(recent_intensities)
                if abs(intensity - avg_intensity) > thresholds["max_intensity"] * 0.1:
                    anomalies.append({
                        "type": "unstable_light_intensity",
                        "value": intensity,
                        "average": avg_intensity
                    })
                    
        elif test_type == "noise_test":
            noise_level = current_data.get("noise_level", 0)
            ambient_level = current_data.get("ambient_level", 0)
            if (noise_level - ambient_level) < 20:  # Minimum difference threshold
                anomalies.append({
                    "type": "insufficient_noise_difference",
                    "value": noise_level,
                    "ambient": ambient_level
                })
                
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
            session["data"]["alerts"].append({
                "type": anomaly["type"],
                "details": anomaly,
                "timestamp": datetime.utcnow()
            })
            
            await self.results_service.store_test_anomaly(
                session_id=session_id,
                anomaly_data=anomaly
            )
            
            await notification_service.send_notification(
                user_id=str(session["data"]["operator_id"]),
                title="Test Anomaly Detected",
                message=f"Anomaly detected: {anomaly['type']}",
                notification_type="anomaly",
                data=anomaly
            )
            
            if session["alert_count"] >= self.alert_threshold:
                await self._handle_critical_alerts(session_id)

    async def _handle_critical_alerts(self, session_id: str) -> None:
        """Handle critical alert situations."""
        try:
            session = self.active_sessions[session_id]
            
            await self.test_service.pause_session(session_id)
            
            await notification_service.send_notification(
                user_id="supervisor",
                title="Critical Test Alerts",
                message=f"Multiple anomalies detected in session {session_id}",
                notification_type="critical",
                data={
                    "session_id": session_id,
                    "alert_count": session["alert_count"],
                    "alerts": session["data"]["alerts"]
                }
            )
            
            await websocket_manager.broadcast_session_event(
                session_id,
                "critical_alert",
                {
                    "alert_count": session["alert_count"],
                    "latest_alerts": session["data"]["alerts"][-3:]
                }
            )
            
            logger.warning(f"Critical alerts handled for session: {session_id}")
            
        except Exception as e:
            logger.error(f"Critical alert handling error: {str(e)}")
            raise MonitoringError(f"Failed to handle critical alerts: {str(e)}")

    async def _verify_test_prerequisites(
        self,
        center_id: str,
        operator_id: str
    ) -> None:
        """Verify all prerequisites for test session."""
        try:
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
                
                last_activity = session["data"]["metadata"]["last_activity"]
                if current_time - last_activity > self.session_timeout:
                    await self._handle_session_timeout(session_id)
                    break
                
                await self._check_data_consistency(session_id)
                
                await self.test_service.check_equipment_status(
                    center_id=str(session["data"]["center_id"])
                )
                
                await asyncio.sleep(5)
                
        except Exception as e:
            logger.error(f"Session monitoring error: {str(e)}")
            await self._handle_session_error(session_id, str(e))

    async def _handle_session_timeout(self, session_id: str) -> None:
        """Handle session timeout by cleaning up and notifying."""
        try:
            session = self.active_sessions[session_id]
            
            await self.test_service.update_session_status(
                session_id=session_id,
                status=TestStatus.FAILED.value,
                reason="Session timeout"
            )
            
            await notification_service.send_notification(
                user_id=str(session["data"]["operator_id"]),
                title="Test Session Timeout",
                message=f"Session {session_id} timed out due to inactivity"
            )
            
            await self._cleanup_session(session_id)
            
        except Exception as e:
            logger.error(f"Session timeout handling error: {str(e)}")
            raise MonitoringError(f"Failed to handle session timeout: {str(e)}")

    async def _handle_session_error(
        self,
        session_id: str,
        error_message: str
    ) -> None:
        """Handle session errors and perform cleanup."""
        try:
            session = self.active_sessions[session_id]
            
            await self.test_service.update_session_status(
                session_id=session_id,
                status=TestStatus.FAILED.value,
                reason=f"Session error: {error_message}"
            )
            
            await notification_service.send_notification(
                user_id=str(session["data"]["operator_id"]),
                title="Test Session Error",
                message=f"Error in session {session_id}: {error_message}",
                notification_type="error"
            )
            
            await self._cleanup_session(session_id)
            
        except Exception as e:
            logger.error(f"Session error handling failed: {str(e)}")

    async def _cleanup_session(self, session_id: str) -> None:
        """Clean up session resources."""
        try:
            if session_id in self.active_sessions:
                session = self.active_sessions[session_id]
                
                if session.get("monitor_task"):
                    session["monitor_task"].cancel()
                    
                if session.get("consistency_task"):
                    session["consistency_task"].cancel()
                    
                if session.get("equipment_task"):
                    session["equipment_task"].cancel()
                    
                await websocket_manager.close_session_connections(session_id)
                
                del self.active_sessions[session_id]
                
                logger.info(f"Cleaned up session: {session_id}")
                
        except Exception as e:
            logger.error(f"Session cleanup error: {str(e)}")

    async def _check_data_consistency(self, session_id: str) -> None:
        """Check test data consistency and sequence."""
        try:
            session = self.active_sessions[session_id]
            current_test = session["data"]["current_test"]
            
            if not current_test:
                return
                
            recent_data = [
                d for d in session["data_buffer"]
                if d["test_type"] == current_test
                and d["timestamp"] > datetime.utcnow() - timedelta(seconds=30)
            ]
            
            if not recent_data:
                await self._handle_data_gap(session_id, current_test)
                
        except Exception as e:
            logger.error(f"Data consistency check error: {str(e)}")
            raise MonitoringError(f"Failed to check data consistency: {str(e)}")

    async def _handle_data_gap(
        self,
        session_id: str,
        test_type: str
    ) -> None:
        """Handle gaps in test data stream."""
        try:
            session = self.active_sessions[session_id]
            
            await notification_service.send_notification(
                user_id=str(session["data"]["operator_id"]),
                title="Data Gap Detected",
                message=f"No data received for {test_type} in last 30 seconds",
                notification_type="warning"
            )
            
            await websocket_manager.broadcast_session_event(
                session_id,
                "data_gap_warning",
                {
                    "test_type": test_type,
                    "timestamp": datetime.utcnow().isoformat()
                }
            )
            
        except Exception as e:
            logger.error(f"Data gap handling error: {str(e)}")

    async def _monitor_equipment(self, session_id: str) -> None:
        """Monitor equipment status during test session."""
        try:
            while session_id in self.active_sessions:
                session = self.active_sessions[session_id]
                
                status = await self.test_service.check_equipment_status(
                    center_id=str(session["data"]["center_id"])
                )
                
                if status.get("issues"):
                    await self._handle_equipment_issues(session_id, status["issues"])
                
                await asyncio.sleep(30)  # Check every 30 seconds
                
        except Exception as e:
            logger.error(f"Equipment monitoring error: {str(e)}")

    async def _handle_equipment_issues(
        self,
        session_id: str,
        issues: List[Dict[str, Any]]
    ) -> None:
        """Handle equipment issues during test."""
        try:
            session = self.active_sessions[session_id]
            
            await notification_service.send_notification(
                user_id=str(session["data"]["operator_id"]),
                title="Equipment Issues Detected",
                message=f"{len(issues)} equipment issues detected",
                notification_type="equipment_warning",
                data={"issues": issues}
            )
            
            if any(issue["severity"] == "critical" for issue in issues):
                await self.test_service.pause_session(session_id)
                
            await websocket_manager.broadcast_session_event(
                session_id,
                "equipment_warning",
                {"issues": issues}
            )
            
        except Exception as e:
            logger.error(f"Equipment issue handling error: {str(e)}")

# Initialize test monitor with required services
test_monitor = TestMonitor(
    test_service=test_service_instance,  # Import from test service module
    results_service=results_service_instance  # Import from results service module
)