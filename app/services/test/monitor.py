# backend/app/services/test/monitor.py

from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import logging
import asyncio
from bson import ObjectId

from ...core.exceptions import ValidationError, MonitoringError
from ...services.websocket.manager import websocket_manager
from ...services.notification.notification_service import notification_service
from ...database import db_manager
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class TestMonitor:
    def __init__(self):
        self.active_sessions: Dict[str, Dict[str, Any]] = {}
        
        # Enhanced validation thresholds with more precise criteria
        self.validation_thresholds = {
            "speed_test": {
                "min_speed": 0,
                "max_speed": 120,
                "min_readings": 10,
                "reading_interval": 0.5,  # seconds
                "stabilization_time": 5,  # seconds
                "deviation_threshold": 2.0  # km/h
            },
            "brake_test": {
                "min_force": 50,  # Newtons
                "max_force": 1000,
                "response_time": 0.75,  # seconds
                "imbalance_limit": 30,  # percent
                "min_deceleration": 5.8  # m/s²
            },
            "headlight_test": {
                "min_intensity": 100,  # candela
                "max_intensity": 1000,
                "max_misalignment": 2.0,  # degrees
                "min_measurements": 5
            },
            "noise_test": {
                "max_level": 85,  # dB
                "ambient_threshold": 45,
                "measurement_duration": 10,  # seconds
                "sample_rate": 10  # readings per second
            }
        }
        
        self.session_timeout = timedelta(minutes=30)
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
            async with db_manager.transaction() as session:
                # Verify prerequisites
                await self._verify_test_prerequisites(center_id, operator_id)

                # Create session record
                session_data = {
                    "session_id": session_id,
                    "vehicle_id": ObjectId(vehicle_id),
                    "center_id": ObjectId(center_id),
                    "operator_id": ObjectId(operator_id),
                    "start_time": datetime.utcnow(),
                    "status": "in_progress",
                    "measurements": {},
                    "alerts": [],
                    "metadata": {
                        "client_connection_count": 0,
                        "data_points_received": 0,
                        "last_activity": datetime.utcnow()
                    }
                }

                # Store session data
                await db_manager.execute_query(
                    "test_sessions",
                    "insert_one",
                    session_data,
                    session=session
                )

                # Initialize monitoring
                self.active_sessions[session_id] = {
                    "data": session_data,
                    "monitor_task": asyncio.create_task(
                        self._monitor_session(session_id)
                    )
                }

                # Notify session start
                await self._notify_session_start(session_data)

                logger.info(f"Started monitoring session: {session_id}")
                return session_data

        except Exception as e:
            logger.error(f"Session start error: {str(e)}")
            raise MonitoringError(f"Failed to start monitoring session: {str(e)}")

    async def process_test_data(
        self,
        session_id: str,
        test_type: str,
        raw_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process and validate incoming test data."""
        try:
            session = self.active_sessions.get(session_id)
            if not session:
                raise MonitoringError("Invalid or expired test session")

            # Validate data
            validated_data = await self.validate_test_data(test_type, raw_data)
            
            # Process measurements
            processed_data = await self._process_measurements(
                test_type,
                validated_data,
                session["data"]["measurements"].get(test_type, [])
            )

            # Update session data
            session["data"]["measurements"].setdefault(test_type, []).append(processed_data)
            session["data"]["metadata"]["data_points_received"] += 1
            session["data"]["metadata"]["last_activity"] = datetime.utcnow()

            # Check for anomalies
            alerts = await self._check_test_thresholds(test_type, processed_data)
            if alerts:
                await self._handle_alerts(session_id, alerts)

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

    async def validate_test_data(
        self,
        test_type: str,
        raw_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Enhanced validation with comprehensive error checking."""
        validation_errors = []
        
        if test_type == "speed_test":
            validation_errors.extend(
                await self._validate_speed_test(raw_data)
            )
        elif test_type == "brake_test":
            validation_errors.extend(
                await self._validate_brake_test(raw_data)
            )
        elif test_type == "headlight_test":
            validation_errors.extend(
                await self._validate_headlight_test(raw_data)
            )
        elif test_type == "noise_test":
            validation_errors.extend(
                await self._validate_noise_test(raw_data)
            )

        if validation_errors:
            await self._handle_validation_errors(validation_errors)
            raise ValidationError(
                f"Test data validation failed: {validation_errors}"
            )

        return self._prepare_validated_data(test_type, raw_data)

    async def _validate_speed_test(
        self,
        data: Dict[str, Any]
    ) -> List[str]:
        """Comprehensive speed test validation."""
        errors = []
        thresholds = self.validation_thresholds["speed_test"]

        readings = data.get("readings", [])
        
        # Check number of readings
        if len(readings) < thresholds["min_readings"]:
            errors.append(
                f"Insufficient readings: {len(readings)} < {thresholds['min_readings']}"
            )

        # Validate reading intervals
        for i in range(1, len(readings)):
            interval = readings[i]["timestamp"] - readings[i-1]["timestamp"]
            if interval > thresholds["reading_interval"] * 1.5:  # Allow 50% margin
                errors.append(f"Invalid reading interval at index {i}: {interval}s")

        # Check speed values
        for i, reading in enumerate(readings):
            speed = reading.get("speed", 0)
            if not thresholds["min_speed"] <= speed <= thresholds["max_speed"]:
                errors.append(
                    f"Speed out of range at index {i}: {speed} km/h"
                )

        # Validate stabilization period
        stable_readings = self._get_stable_readings(readings, thresholds)
        if not stable_readings:
            errors.append("No stable speed readings found")

        return errors

    async def _verify_test_prerequisites(
        self,
        center_id: str,
        operator_id: str
    ) -> None:
        """Verify all prerequisites are met before starting test."""
        try:
            # Verify center status
            center = await db_manager.execute_query(
                "centers",
                "find_one",
                {"_id": ObjectId(center_id)}
            )
            if not center or center["status"] != "active":
                raise MonitoringError("Invalid or inactive test center")

            # Verify operator permissions
            operator = await db_manager.execute_query(
                "users",
                "find_one",
                {"_id": ObjectId(operator_id)}
            )
            if not operator or "conduct_tests" not in operator.get("permissions", []):
                raise MonitoringError("Operator not authorized to conduct tests")

            # Verify equipment status
            equipment_status = await self._check_equipment_status(center_id)
            if not equipment_status["all_operational"]:
                raise MonitoringError(
                    f"Equipment check failed: {equipment_status['details']}"
                )

        except Exception as e:
            logger.error(f"Prerequisites verification error: {str(e)}")
            raise MonitoringError(f"Failed to verify test prerequisites: {str(e)}")

    async def _monitor_session(self, session_id: str) -> None:
        """Monitor test session for timeout and anomalies."""
        try:
            while session_id in self.active_sessions:
                session = self.active_sessions[session_id]
                current_time = datetime.utcnow()
                
                # Check session timeout
                if (current_time - session["data"]["metadata"]["last_activity"] 
                    > self.session_timeout):
                    await self._handle_session_timeout(session_id)
                    break

                # Check data consistency
                await self._check_data_consistency(session_id)

                await asyncio.sleep(5)  # Check every 5 seconds

        except Exception as e:
            logger.error(f"Session monitoring error: {str(e)}")
            await self._handle_session_error(session_id, str(e))

    async def _handle_session_timeout(self, session_id: str) -> None:
        """Handle session timeout with proper cleanup."""
        try:
            session = self.active_sessions[session_id]
            
            # Update session status
            await db_manager.execute_query(
                "test_sessions",
                "update_one",
                {"_id": ObjectId(session_id)},
                {"$set": {
                    "status": "timeout",
                    "end_time": datetime.utcnow(),
                    "timeout_reason": "Session inactivity timeout"
                }}
            )
            
            # Notify timeout
            await notification_service.send_notification(
                user_id=str(session["data"]["operator_id"]),
                title="Test Session Timeout",
                message=f"Test session {session_id} has timed out due to inactivity"
            )

            # Cleanup session
            await self._cleanup_session(session_id)

        except Exception as e:
            logger.error(f"Session timeout handling error: {str(e)}")

    async def _cleanup_session(self, session_id: str) -> None:
        """Clean up session resources."""
        try:
            if session_id in self.active_sessions:
                # Cancel monitoring task
                self.active_sessions[session_id]["monitor_task"].cancel()
                
                # Clear session data
                del self.active_sessions[session_id]
                
                logger.info(f"Cleaned up session: {session_id}")
                
        except Exception as e:
            logger.error(f"Session cleanup error: {str(e)}")

# Initialize test monitor
test_monitor = TestMonitor()