from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import logging
from bson import ObjectId
import json

from ...core.exceptions import TestError
from ...models.test import TestSession, TestType
from .interfaces import TestMonitorInterface, TestResultsInterface
from ...services.websocket import websocket_manager
from ...services.vehicle import vehicle_service
from ...services.s3 import s3_service
from ...database import get_database
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class TestService:
    """Service for managing vehicle test operations with integrated monitoring."""
    
    def __init__(
        self,
        test_monitor: TestMonitorInterface,
        results_service: TestResultsInterface
    ):
        """Initialize test service with monitoring and results interfaces."""
        self.test_monitor = test_monitor
        self.results_service = results_service
        self.db = None
        
        # Define test thresholds and parameters
        self.test_parameters = {
            TestType.SPEED: {
                "min_speed": 0,
                "max_speed": 120,
                "target_speed": 60,
                "tolerance": 2.0
            },
            TestType.BRAKE: {
                "min_force": 0,
                "max_force": 1000,
                "min_efficiency": 50,
                "max_imbalance": 30
            },
            TestType.NOISE: {
                "max_level": 90,
                "warning_level": 85,
                "measurement_count": 3
            },
            TestType.HEADLIGHT: {
                "min_intensity": 0,
                "max_intensity": 1000,
                "max_glare": 50,
                "angle_tolerance": 2.0
            }
        }
        
        logger.info("Test service initialized with monitoring integration")

    async def create_test_session(
        self,
        vehicle_id: str,
        center_id: str,
        operator_id: str
    ) -> Dict[str, Any]:
        """Create and initialize a new test session."""
        try:
            db = await get_database()
            
            # Generate unique session code
            session_code = await self._generate_session_code(center_id)
            
            # Create initial session document
            session_doc = {
                "sessionCode": session_code,
                "vehicleId": ObjectId(vehicle_id),
                "atsCenterId": ObjectId(center_id),
                "testedBy": ObjectId(operator_id),
                "status": "created",
                "testDate": datetime.utcnow(),
                "testResults": {
                    "visualInspection": None,
                    "speedTest": None,
                    "brakeTest": None,
                    "noiseTest": None,
                    "headlightTest": None,
                    "axleTest": None
                },
                "createdAt": datetime.utcnow(),
                "updatedAt": datetime.utcnow()
            }
            
            # Insert session
            result = await db.testSessions.insert_one(session_doc)
            session_doc["_id"] = result.inserted_id
            
            # Start monitoring through interface
            monitored_session = await self.test_monitor.start_monitoring_session(
                session_id=str(result.inserted_id),
                vehicle_id=vehicle_id,
                center_id=center_id,
                operator_id=operator_id
            )
            
            logger.info(f"Created test session: {session_code}")
            return monitored_session
            
        except Exception as e:
            logger.error(f"Session creation error: {str(e)}")
            raise TestError(str(e))

    async def start_test_session(
        self,
        session_id: str,
        started_by: str
    ) -> Dict[str, Any]:
        """Start a test session."""
        try:
            db = await get_database()
            
            # Update session status
            result = await db.testSessions.find_one_and_update(
                {
                    "_id": ObjectId(session_id),
                    "status": "created"
                },
                {
                    "$set": {
                        "status": "in_progress",
                        "startTime": datetime.utcnow(),
                        "updatedAt": datetime.utcnow(),
                        "startedBy": ObjectId(started_by)
                    }
                },
                return_document=True
            )
            
            if not result:
                raise TestError("Session not found or already started")
            
            # Update monitoring status
            await self.test_monitor.process_test_data(
                session_id=session_id,
                test_type="session_start",
                raw_data={"started_by": started_by}
            )
            
            # Notify clients
            await websocket_manager.broadcast_status_update(
                session_id,
                "started",
                {
                    "session_code": result["sessionCode"],
                    "start_time": result["startTime"]
                }
            )
            
            logger.info(f"Started test session: {session_id}")
            return result
            
        except Exception as e:
            logger.error(f"Session start error: {str(e)}")
            raise TestError("Failed to start test session")

    async def process_test_data(
        self,
        session_id: str,
        test_type: str,
        data: Dict[str, Any],
        images: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Process and validate test data."""
        try:
            # Validate data against thresholds
            validated_data = await self._validate_test_data(test_type, data)
            
            # Process test-specific measurements
            processed_data = await self._process_test_measurements(
                test_type,
                validated_data
            )
            
            # Store images if provided
            if images:
                image_urls = await self._store_test_images(
                    session_id,
                    test_type,
                    images
                )
                processed_data["images"] = image_urls
            
            # Process through monitor
            monitored_data = await self.test_monitor.process_test_data(
                session_id=session_id,
                test_type=test_type,
                raw_data=processed_data
            )
            
            # Store results
            await self.results_service.store_test_result(
                session_id=session_id,
                test_type=test_type,
                result_data=monitored_data
            )
            
            logger.info(f"Processed {test_type} data for session: {session_id}")
            return monitored_data
            
        except Exception as e:
            logger.error(f"Data processing error: {str(e)}")
            raise TestError("Failed to process test data")

    async def complete_test_session(
        self,
        session_id: str,
        completed_by: str
    ) -> Dict[str, Any]:
        """Complete a test session and generate results."""
        try:
            db = await get_database()
            
            # Get final monitored data
            final_data = await self.test_monitor.process_test_data(
                session_id=session_id,
                test_type="session_complete",
                raw_data={"completed_by": completed_by}
            )
            
            # Calculate final results
            final_results = await self._calculate_final_results(final_data)
            
            # Update session status
            result = await db.testSessions.find_one_and_update(
                {
                    "_id": ObjectId(session_id),
                    "status": "in_progress"
                },
                {
                    "$set": {
                        "status": "completed",
                        "endTime": datetime.utcnow(),
                        "finalResults": final_results,
                        "completedBy": ObjectId(completed_by),
                        "updatedAt": datetime.utcnow()
                    }
                },
                return_document=True
            )
            
            if not result:
                raise TestError("Session not found or not in progress")
            
            # Generate test report
            report_url = await self._generate_test_report(result)
            
            # Store final results
            await self.results_service.store_final_results(
                session_id=session_id,
                results_data=final_results,
                report_url=report_url
            )
            
            # Update vehicle test history
            await vehicle_service.add_test_record(
                result["vehicleId"],
                session_id
            )
            
            # Notify clients
            await websocket_manager.broadcast_status_update(
                session_id,
                "completed",
                {
                    "final_results": final_results,
                    "report_url": report_url
                }
            )
            
            logger.info(f"Completed test session: {session_id}")
            return result
            
        except Exception as e:
            logger.error(f"Session completion error: {str(e)}")
            raise TestError("Failed to complete test session")

    async def _validate_test_data(
        self,
        test_type: str,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate test data against defined thresholds."""
        parameters = self.test_parameters[test_type]
        validated_data = {}
        
        if test_type == TestType.SPEED:
            speed = float(data.get('speed', 0))
            if not (parameters['min_speed'] <= speed <= parameters['max_speed']):
                raise TestError(f"Speed value {speed} out of valid range")
            validated_data['speed'] = speed
            
        elif test_type == TestType.BRAKE:
            force = float(data.get('force', 0))
            if not (parameters['min_force'] <= force <= parameters['max_force']):
                raise TestError(f"Brake force {force} out of valid range")
            validated_data['force'] = force
            
        return validated_data

    async def _process_test_measurements(
        self,
        test_type: str,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process test-specific measurements."""
        processed_data = {
            'timestamp': datetime.utcnow(),
            'raw_data': data
        }
        
        parameters = self.test_parameters[test_type]
        
        if test_type == TestType.SPEED:
            processed_data.update({
                'current_speed': data['speed'],
                'target_speed': parameters['target_speed'],
                'deviation': abs(data['speed'] - parameters['target_speed'])
            })
            
        elif test_type == TestType.BRAKE:
            processed_data.update({
                'brake_force': data['force'],
                'efficiency': (data['force'] / parameters['max_force']) * 100
            })
            
        return processed_data

    async def _store_test_images(
        self,
        session_id: str,
        test_type: str,
        images: List[Dict[str, Any]]
    ) -> List[str]:
        """Store test images in S3."""
        image_urls = []
        
        try:
            for image in images:
                url = await s3_service.upload_document(
                    file=image['file'],
                    folder=f"tests/{session_id}/{test_type}",
                    metadata={
                        "session_id": session_id,
                        "test_type": test_type,
                        "image_type": image.get('type', 'general')
                    }
                )
                image_urls.append(url)
                
            return image_urls
            
        except Exception as e:
            logger.error(f"Image storage error: {str(e)}")
            raise TestError("Failed to store test images")

    async def _calculate_final_results(
        self,
        session_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Calculate final test results and recommendations."""
        try:
            # Implementation for results calculation
            pass
            
        except Exception as e:
            logger.error(f"Results calculation error: {str(e)}")
            raise TestError("Failed to calculate final results")

    async def _generate_test_report(
        self,
        session_data: Dict[str, Any]
    ) -> str:
        """Generate detailed test report PDF."""
        try:
            # Implementation for report generation
            pass
            
        except Exception as e:
            logger.error(f"Report generation error: {str(e)}")
            raise TestError("Failed to generate test report")

# Initialize test service with required interfaces
test_service = TestService()