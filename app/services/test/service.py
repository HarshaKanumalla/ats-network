from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import logging
from bson import ObjectId
import json
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from io import BytesIO

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
                "measurement_count": 3,
                "ambient_threshold": 45
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
            
            # Validate vehicle eligibility
            if not await self._validate_vehicle_eligibility(vehicle_id):
                raise TestError("Vehicle not eligible for testing")
            
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

    async def _generate_session_code(self, center_id: str) -> str:
        """Generate unique session code."""
        try:
            db = await get_database()
            
            # Get center code
            center = await db.atsCenters.find_one({"_id": ObjectId(center_id)})
            if not center:
                raise TestError("Invalid center ID")
                
            center_code = center.get("code", "ATS")
            
            # Get current date components
            now = datetime.utcnow()
            date_code = now.strftime("%y%m%d")
            
            # Get count of sessions for today
            today_start = datetime.combine(now.date(), datetime.min.time())
            session_count = await db.testSessions.count_documents({
                "atsCenterId": ObjectId(center_id),
                "createdAt": {"$gte": today_start}
            })
            
            # Generate sequential number
            sequence = str(session_count + 1).zfill(4)
            
            # Combine components
            session_code = f"{center_code}-{date_code}-{sequence}"
            
            return session_code
            
        except Exception as e:
            logger.error(f"Session code generation error: {str(e)}")
            raise TestError("Failed to generate session code")

    async def _validate_vehicle_eligibility(self, vehicle_id: str) -> bool:
        """Validate if vehicle is eligible for testing."""
        try:
            db = await get_database()
            
            # Get vehicle details
            vehicle = await db.vehicles.find_one({"_id": ObjectId(vehicle_id)})
            if not vehicle:
                raise TestError("Vehicle not found")
                
            # Check if vehicle has pending tests
            pending_test = await db.testSessions.find_one({
                "vehicleId": ObjectId(vehicle_id),
                "status": {"$in": ["created", "in_progress"]}
            })
            
            if pending_test:
                raise TestError("Vehicle has pending test session")
                
            # Check test history
            last_test = await db.testSessions.find_one({
                "vehicleId": ObjectId(vehicle_id),
                "status": "completed"
            }, sort=[("testDate", -1)])
            
            if last_test:
                # Check if minimum interval between tests is maintained
                min_interval = timedelta(days=settings.MIN_TEST_INTERVAL_DAYS)
                if datetime.utcnow() - last_test["testDate"] < min_interval:
                    raise TestError("Minimum interval between tests not met")
            
            return True
            
        except Exception as e:
            logger.error(f"Eligibility check error: {str(e)}")
            raise TestError(f"Failed to check vehicle eligibility: {str(e)}")

    async def _validate_test_data(
        self,
        test_type: str,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate test data against defined thresholds."""
        parameters = self.test_parameters[test_type]
        validated_data = {}
        
        try:
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
                validated_data['response_time'] = float(data.get('response_time', 0))
                
            elif test_type == TestType.NOISE:
                noise_level = float(data.get('noise_level', 0))
                ambient_level = float(data.get('ambient_level', 0))
                
                if ambient_level > parameters['ambient_threshold']:
                    raise TestError(f"Ambient noise {ambient_level} too high")
                    
                if noise_level > parameters['max_level']:
                    raise TestError(f"Noise level {noise_level} exceeds maximum")
                    
                validated_data['noise_level'] = noise_level
                validated_data['ambient_level'] = ambient_level
                
            elif test_type == TestType.HEADLIGHT:
                intensity = float(data.get('intensity', 0))
                glare = float(data.get('glare', 0))
                angle = float(data.get('angle', 0))
                
                if not (parameters['min_intensity'] <= intensity <= parameters['max_intensity']):
                    raise TestError(f"Light intensity {intensity} out of valid range")
                    
                if glare > parameters['max_glare']:
                    raise TestError(f"Glare {glare} exceeds maximum")
                    
                if abs(angle) > parameters['angle_tolerance']:
                    raise TestError(f"Angle {angle} exceeds tolerance")
                    
                validated_data['intensity'] = intensity
                validated_data['glare'] = glare
                validated_data['angle'] = angle
            
            return validated_data
            
        except ValueError as e:
            raise TestError(f"Invalid data format: {str(e)}")
            
        except Exception as e:
            logger.error(f"Data validation error: {str(e)}")
            raise TestError(f"Failed to validate {test_type} data: {str(e)}")

    async def _calculate_final_results(
        self,
        session_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Calculate final test results and recommendations."""
        try:
            test_results = session_data.get("testResults", {})
            final_results = {
                "overall_status": "passed",
                "failed_tests": [],
                "warnings": [],
                "measurements": {},
                "recommendations": []
            }
            
            # Process each test type
            for test_type, data in test_results.items():
                if not data:
                    continue
                    
                test_status = data.get("status")
                measurements = data.get("measurements", {})
                
                # Store measurements
                final_results["measurements"][test_type] = measurements
                
                # Check failures
                if test_status == "failed":
                    final_results["overall_status"] = "failed"
                    final_results["failed_tests"].append({
                        "test_type": test_type,
                        "failures": data.get("failures", [])
                    })
                
                # Process specific test types
                if test_type == TestType.BRAKE:
                    efficiency = data.get("efficiency", 0)
                    if efficiency < 70:
                        final_results["recommendations"].append(
                            "Brake system maintenance recommended"
                        )
                    if efficiency < 50:
                        final_results["warnings"].append(
                            "Critical brake efficiency issue detected"
                        )
                        
                elif test_type == TestType.HEADLIGHT:
                    if any(h.get("max_glare", 0) > 45 for h in [
                        data.get("left_headlight", {}),
                        data.get("right_headlight", {})
                    ]):
                        final_results["warnings"].append(
                            "High headlight glare detected"
                        )
                        final_results["recommendations"].append(
                            "Headlight adjustment recommended"
                        )
                        
                elif test_type == TestType.NOISE:
                    avg_noise = data.get("average_noise", 0)
                    if avg_noise > 80:
                        final_results["recommendations"].append(
                            "Vehicle noise reduction recommended"
                        )
                    if avg_noise > 85:
                        final_results["warnings"].append(
                            "Excessive vehicle noise detected"
                        )
            
            return final_results
            
        except Exception as e:
            logger.error(f"Results calculation error: {str(e)}")
            raise TestError("Failed to calculate final results")

    async def _generate_test_report(
        self,
        session_data: Dict[str, Any]
    ) -> str:
        """Generate detailed test report PDF."""
        try:
            # Create PDF buffer
            buffer = BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=letter)
            story = []
            styles = getSampleStyleSheet()
            
            # Add header
            story.append(Paragraph(
                f"Vehicle Test Report - {session_data['sessionCode']}",
                styles['Heading1']
            ))
            
            # Add test info
            test_info = [
                ["Test Date", session_data['testDate'].strftime("%Y-%m-%d %H:%M")],
                ["Vehicle ID", str(session_data['vehicleId'])],
                ["Center ID", str(session_data['atsCenterId'])],
                ["Status", session_data.get('finalResults', {}).get('overall_status', 'N/A')]
            ]
            
            info_table = Table(test_info)
            info_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.lightgrey),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 12),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            story.append(info_table)
            
            # Add test results
            final_results = session_data.get('finalResults', {})
            for test_type, measurements in final_results.get('measurements', {}).items():
                story.append(Paragraph(f"\n{test_type} Test Results", styles['Heading2']))
                
                result_data = []
                for key, value in measurements.items():
                    if isinstance(value, (int, float)):
                        result_data.append([key.replace('_', ' ').title(), f"{value:.2f}"])
                
                if result_data:
                    result_table = Table(result_data)
                    result_table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, -1), colors.white),
                        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
                        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                        ('FONTSIZE', (0, 0), (-1, -1), 10),
                        ('GRID', (0, 0), (-1, -1), 1, colors.black)
                    ]))
                    story.append(result_table)
            
            # Add warnings and recommendations
            if final_results.get('warnings'):
                story.append(Paragraph("\nWarnings", styles['Heading2']))
                for warning in final_results['warnings']:
                    story.append(Paragraph(f"• {warning}", styles['Normal']))
            
            if final_results.get('recommendations'):
                story.append(Paragraph("\nRecommendations", styles['Heading2']))
                for rec in final_results['recommendations']:
                    story.append(Paragraph(f"• {rec}", styles['Normal']))
            
            # Generate PDF
            doc.build(story)
            
            # Upload to S3
            pdf_data = buffer.getvalue()
            report_url = await s3_service.upload_document(
                file=pdf_data,
                folder=f"reports/{session_data['_id']}",
                filename=f"{session_data['sessionCode']}_report.pdf",
                content_type='application/pdf'
            )
            
            return report_url
            
        except Exception as e:
            logger.error(f"Report generation error: {str(e)}")
            raise TestError("Failed to generate test report")

# Initialize test service with required interfaces
test_service = TestService(
    test_monitor=test_monitor_instance,    # Import from test monitor module
    results_service=results_service_instance  # Import from results service module
)