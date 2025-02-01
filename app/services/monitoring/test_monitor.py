# backend/app/services/monitoring/test_monitor.py

from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import logging
import asyncio
from bson import ObjectId

from ...core.exceptions import MonitoringError
from ...services.websocket import websocket_manager
from ...services.notification import notification_service
from ...database import get_database, database_transaction
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class TestMonitoringService:
    def __init__(self):
        self.active_sessions: Dict[str, Dict[str, Any]] = {}
        self.test_thresholds = {
            "speed": {
                "min_speed": 0,
                "max_speed": 120,
                "target_speed": 60,
                "tolerance": 2.0,
                "measurement_interval": 0.5  # seconds
            },
            "brake": {
                "min_force": 0,
                "max_force": 1000,
                "min_efficiency": 50,
                "max_imbalance": 30,
                "measurement_count": 3
            },
            "noise": {
                "max_level": 90,
                "warning_level": 85,
                "min_readings": 3,
                "max_variance": 5
            },
            "headlight": {
                "min_intensity": 0,
                "max_intensity": 1000,
                "max_glare": 50,
                "angle_tolerance": 2.0
            },
            "axle": {
                "max_weight": 5000,
                "max_imbalance": 10,
                "measurement_points": 4
            }
        }
        self.session_timeout = timedelta(minutes=30)
        logger.info("Test monitoring service initialized")

    async def start_test_session(
        self,
        session_id: str,
        vehicle_id: str,
        center_id: str,
        operator_id: str
    ) -> Dict[str, Any]:
        """Initialize and start a new test session with proper monitoring."""
        try:
            async with database_transaction() as session:
                db = await get_database()
                
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
                await db.test_sessions.insert_one(session_data, session=session)
                
                # Initialize real-time monitoring
                self.active_sessions[session_id] = {
                    "data": session_data,
                    "monitor_task": asyncio.create_task(
                        self._monitor_session(session_id)
                    )
                }

                # Notify relevant parties
                await self._notify_session_start(session_data)

                logger.info(f"Started test session: {session_id}")
                return session_data

        except Exception as e:
            logger.error(f"Session start error: {str(e)}")
            raise MonitoringError(f"Failed to start test session: {str(e)}")

    async def process_test_data(
        self,
        session_id: str,
        test_type: str,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process and validate incoming test data in real-time."""
        try:
            session = self.active_sessions.get(session_id)
            if not session:
                raise MonitoringError("Invalid or expired test session")

            # Validate data against thresholds
            validated_data = await self._validate_test_data(test_type, data)
            
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

            # Check for anomalies and generate alerts
            alerts = await self._check_test_thresholds(test_type, processed_data)
            if alerts:
                await self._handle_alerts(session_id, alerts)

            # Broadcast update through WebSocket
            await websocket_manager.broadcast_test_data(
                session_id,
                test_type,
                processed_data
            )

            return processed_data

        except Exception as e:
            logger.error(f"Data processing error: {str(e)}")
            raise MonitoringError(f"Failed to process test data: {str(e)}")

    async def _validate_test_data(
        self,
        test_type: str,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate test data against defined thresholds."""
        thresholds = self.test_thresholds.get(test_type)
        if not thresholds:
            raise MonitoringError(f"Invalid test type: {test_type}")

        validated_data = {}
        
        if test_type == "speed":
            speed = float(data.get("speed", 0))
            if not (thresholds["min_speed"] <= speed <= thresholds["max_speed"]):
                raise MonitoringError(f"Speed value {speed} out of valid range")
            validated_data["speed"] = speed
            validated_data["timestamp"] = datetime.utcnow()

        # Add validation for other test types...

        return validated_data

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
            await self._update_session_status(session_id, "timeout")
            
            # Notify relevant parties
            await notification_service.send_notification(
                user_id=str(session["data"]["operator_id"]),
                title="Test Session Timeout",
                message=f"Test session {session_id} has timed out due to inactivity",
                notification_type="test_alert"
            )

            # Clean up session
            await self._cleanup_session(session_id)

        except Exception as e:
            logger.error(f"Session timeout handling error: {str(e)}")

# Initialize service
test_monitoring_service = TestMonitoringService()