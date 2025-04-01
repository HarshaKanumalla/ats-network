from datetime import datetime
from typing import Dict, Any, List, Optional
import logging
import json
from bson import ObjectId
from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet

from ...core.exceptions import TestResultError
from ...services.s3.s3_service import s3_service
from ...services.notification.notification_service import notification_service
from ...database import db_manager, database_transaction
from ...config import get_settings
from .interfaces import TestServiceInterface, TestMonitorInterface

logger = logging.getLogger(__name__)
settings = get_settings()

class TestResultsService:
    """Service for processing and analyzing test results with interface integration."""
    
    def __init__(
        self,
        test_service: TestServiceInterface,
        test_monitor: TestMonitorInterface
    ):
        """Initialize results service with test service and monitor interfaces."""
        self.test_service = test_service
        self.test_monitor = test_monitor
        self.db = None
        
        # Define test criteria and thresholds
        self.test_criteria = {
            "speed_test": {
                "speed_tolerance": 2.0,
                "min_readings": 5,
                "stabilization_period": 3,  # seconds
                "pass_threshold": 0.95  # 95% compliance
            },
            "brake_test": {
                "min_brake_force": 50,
                "max_imbalance": 30,
                "min_deceleration": 5.8,
                "reaction_time_limit": 0.75  # seconds
            },
            "headlight_test": {
                "min_intensity": 100,
                "max_intensity": 1000,
                "max_glare": 50,
                "angle_tolerance": 2.0
            },
            "noise_test": {
                "max_level": 85,
                "ambient_threshold": 45,
                "measurement_duration": 10  # seconds
            }
        }
        
        logger.info("Test results service initialized with interface integration")

    async def process_test_results(
        self,
        session_id: str,
        test_data: Dict[str, Any],
        operator_id: str
    ) -> Dict[str, Any]:
        """Process and validate complete test results with comprehensive analysis."""
        async with database_transaction() as session:
            try:
                # Validate data completeness
                await self.validate_test_data_completeness(test_data)
                
                # Validate and analyze test data
                analysis_results = await self._analyze_test_data(test_data)
                
                # Determine overall test status
                overall_status = await self._determine_test_status(analysis_results)
                
                # Generate final results
                final_results = {
                    "session_id": session_id,
                    "test_results": analysis_results,
                    "overall_status": overall_status,
                    "operator_id": ObjectId(operator_id),
                    "completion_time": datetime.utcnow(),
                    "metadata": {
                        "test_duration": test_data.get("duration"),
                        "ambient_conditions": test_data.get("ambient_conditions"),
                        "equipment_status": test_data.get("equipment_status")
                    }
                }

                # Update test service
                await self.test_service.update_test_data(
                    session_id=session_id,
                    test_type="results",
                    data=final_results,
                    updated_by=operator_id
                )

                # Store results in database
                await db_manager.execute_query(
                    collection="test_results",
                    operation="insert_one",
                    query=final_results,
                    session=session
                )

                # Generate and store test report
                report_url = await self._generate_test_report(session_id, final_results)
                
                # Update test session status
                await self._update_session_status(
                    session_id,
                    overall_status,
                    report_url,
                    session
                )

                # Send notifications
                await self._send_result_notifications(
                    session_id,
                    overall_status,
                    report_url
                )

                # Update monitoring status
                await self.test_monitor.process_test_data(
                    session_id=session_id,
                    test_type="results_complete",
                    raw_data={
                        "status": overall_status,
                        "report_url": report_url
                    }
                )

                logger.info(f"Processed test results for session: {session_id}")
                return final_results

            except Exception as e:
                logger.error(f"Test result processing error: {str(e)}")
                raise TestResultError(f"Failed to process test results: {str(e)}")

    async def _analyze_test_data(self, test_data: Dict[str, Any]) -> Dict[str, Any]:
        """Perform detailed analysis of test measurements."""
        analysis_results = {}
        
        # Speed test analysis
        if "speed_test" in test_data:
            speed_analysis = await self._analyze_speed_test(test_data["speed_test"])
            analysis_results["speed_test"] = speed_analysis

        # Brake test analysis
        if "brake_test" in test_data:
            brake_analysis = await self._analyze_brake_test(test_data["brake_test"])
            analysis_results["brake_test"] = brake_analysis

        # Headlight test analysis
        if "headlight_test" in test_data:
            headlight_analysis = await self._analyze_headlight_test(
                test_data["headlight_test"]
            )
            analysis_results["headlight_test"] = headlight_analysis

        # Noise test analysis
        if "noise_test" in test_data:
            noise_analysis = await self._analyze_noise_test(test_data["noise_test"])
            analysis_results["noise_test"] = noise_analysis

        return analysis_results

    async def _analyze_speed_test(self, speed_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze speed test measurements with statistical validation."""
        criteria = self.test_criteria["speed_test"]
        
        try:
            readings = speed_data.get("readings", [])
            if len(readings) < criteria["min_readings"]:
                return {
                    "status": "failed",
                    "reason": "Insufficient readings",
                    "measurements": []
                }

            # Filter readings after stabilization period
            stable_readings = [
                r for r in readings 
                if r["timestamp"] >= speed_data["start_time"] + criteria["stabilization_period"]
            ]

            # Calculate statistics
            speeds = [r["speed"] for r in stable_readings]
            avg_speed = sum(speeds) / len(speeds)
            target_speed = speed_data["target_speed"]
            
            # Check compliance
            compliant_readings = [
                s for s in speeds 
                if abs(s - target_speed) <= criteria["speed_tolerance"]
            ]
            compliance_rate = len(compliant_readings) / len(speeds)

            return {
                "status": "passed" if compliance_rate >= criteria["pass_threshold"] else "failed",
                "average_speed": round(avg_speed, 2),
                "target_speed": target_speed,
                "compliance_rate": round(compliance_rate * 100, 2),
                "measurements": stable_readings
            }

        except Exception as e:
            logger.error(f"Speed test analysis error: {str(e)}")
            raise TestResultError(f"Failed to analyze speed test: {str(e)}")

    async def _analyze_brake_test(self, brake_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze brake test measurements with force and timing validation."""
        criteria = self.test_criteria["brake_test"]
        
        try:
            measurements = brake_data.get("measurements", [])
            if not measurements:
                return {
                    "status": "failed",
                    "reason": "No measurements recorded",
                    "measurements": []
                }

            # Analyze brake force
            max_force = max(m["force"] for m in measurements)
            min_force = min(m["force"] for m in measurements)
            avg_force = sum(m["force"] for m in measurements) / len(measurements)
            
            # Calculate imbalance
            imbalance = ((max_force - min_force) / max_force) * 100
            
            # Analyze reaction time
            reaction_times = [m["reaction_time"] for m in measurements]
            avg_reaction_time = sum(reaction_times) / len(reaction_times)
            
            # Calculate deceleration
            deceleration = brake_data.get("deceleration", 0)
            
            # Determine status
            status = "passed"
            failures = []
            
            if avg_force < criteria["min_brake_force"]:
                status = "failed"
                failures.append("Insufficient brake force")
                
            if imbalance > criteria["max_imbalance"]:
                status = "failed"
                failures.append("Brake force imbalance too high")
                
            if avg_reaction_time > criteria["reaction_time_limit"]:
                status = "failed"
                failures.append("Reaction time too slow")
                
            if deceleration < criteria["min_deceleration"]:
                status = "failed"
                failures.append("Insufficient deceleration")

            return {
                "status": status,
                "failures": failures if status == "failed" else [],
                "average_force": round(avg_force, 2),
                "max_force": round(max_force, 2),
                "imbalance": round(imbalance, 2),
                "average_reaction_time": round(avg_reaction_time, 3),
                "deceleration": round(deceleration, 2),
                "measurements": measurements
            }

        except Exception as e:
            logger.error(f"Brake test analysis error: {str(e)}")
            raise TestResultError(f"Failed to analyze brake test: {str(e)}")

    async def _analyze_headlight_test(
        self,
        headlight_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Analyze headlight test measurements with intensity and alignment checks."""
        criteria = self.test_criteria["headlight_test"]
        
        try:
            left_measurements = headlight_data.get("left", [])
            right_measurements = headlight_data.get("right", [])
            
            if not left_measurements or not right_measurements:
                return {
                    "status": "failed",
                    "reason": "Incomplete measurements",
                    "measurements": {}
                }

            def analyze_single_headlight(measurements):
                intensities = [m["intensity"] for m in measurements]
                avg_intensity = sum(intensities) / len(intensities)
                
                glare_readings = [m["glare"] for m in measurements]
                max_glare = max(glare_readings)
                
                angles = [m["angle"] for m in measurements]
                avg_angle = sum(angles) / len(angles)
                
                return {
                    "average_intensity": round(avg_intensity, 2),
                    "max_glare": round(max_glare, 2),
                    "average_angle": round(avg_angle, 2)
                }

            left_analysis = analyze_single_headlight(left_measurements)
            right_analysis = analyze_single_headlight(right_measurements)
            
            # Determine status
            status = "passed"
            failures = []
            
            for side, analysis in [("left", left_analysis), ("right", right_analysis)]:
                if not (criteria["min_intensity"] <= analysis["average_intensity"] <= criteria["max_intensity"]):
                    status = "failed"
                    failures.append(f"{side.capitalize()} headlight intensity out of range")
                
                if analysis["max_glare"] > criteria["max_glare"]:
                    status = "failed"
                    failures.append(f"{side.capitalize()} headlight glare too high")
                
                if abs(analysis["average_angle"]) > criteria["angle_tolerance"]:
                    status = "failed"
                    failures.append(f"{side.capitalize()} headlight misaligned")

            return {
                "status": status,
                "failures": failures if status == "failed" else [],
                "left_headlight": left_analysis,
                "right_headlight": right_analysis,
                "measurements": {
                    "left": left_measurements,
                    "right": right_measurements
                }
            }

        except Exception as e:
            logger.error(f"Headlight test analysis error: {str(e)}")
            raise TestResultError(f"Failed to analyze headlight test: {str(e)}")

    async def _analyze_noise_test(
        self,
        noise_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Analyze noise test measurements with ambient noise compensation."""
        criteria = self.test_criteria["noise_test"]
        
        try:
            measurements = noise_data.get("measurements", [])
            if len(measurements) < criteria["measurement_duration"]:
                return {
                    "status": "failed",
                    "reason": "Insufficient measurement duration",
                    "measurements": []
                }

            # Analyze noise levels
            noise_levels = [m["noise_level"] for m in measurements]
            ambient_levels = [m["ambient_level"] for m in measurements]
            
            avg_noise = sum(noise_levels) / len(noise_levels)
            avg_ambient = sum(ambient_levels) / len(ambient_levels)
            max_noise = max(noise_levels)
            
            # Calculate noise differential
            noise_differential = avg_noise - avg_ambient
            
            # Determine status
            status = "passed"
            failures = []
            
            if avg_ambient > criteria["ambient_threshold"]:
                status = "failed"
                failures.append("Ambient noise too high")
            
            if max_noise > criteria["max_level"]:
                status = "failed"
                failures.append("Maximum noise level exceeded")
            
            if noise_differential < 20:  # Minimum difference threshold
                status = "failed"
                failures.append("Insufficient noise differential")

            return {
                "status": status,
                "failures": failures if status == "failed" else [],
                "average_noise": round(avg_noise, 2),
                "max_noise": round(max_noise, 2),
                "average_ambient": round(avg_ambient, 2),
                "noise_differential": round(noise_differential, 2),
                "measurements": measurements
            }

        except Exception as e:
            logger.error(f"Noise test analysis error: {str(e)}")
            raise TestResultError(f"Failed to analyze noise test: {str(e)}")

    async def _determine_test_status(
        self,
        analysis_results: Dict[str, Any]
    ) -> str:
        """Determine overall test status based on individual test results."""
        try:
            # Check if any test failed
            for test_type, results in analysis_results.items():
                if results.get("status") == "failed":
                    return "failed"
            
            return "passed"
            
        except Exception as e:
            logger.error(f"Status determination error: {str(e)}")
            raise TestResultError(f"Failed to determine test status: {str(e)}")

    async def _generate_test_report(
        self,
        session_id: str,
        results: Dict[str, Any]
    ) -> str:
        """Generate detailed test report document."""
        try:
            # Get test session details
            session_data = await self._get_test_session_data(session_id)
            
            # Generate report content
            report_data = {
                "session_info": session_data,
                "test_results": results,
                "generated_at": datetime.utcnow().isoformat()
            }

            # Generate PDF report
            report_content = await self._generate_pdf_report(report_data)
            
            # Store report in S3
            report_url = await s3_service.upload_document(
                file=report_content,
                folder=f"test_reports/{session_id}",
                metadata={
                    "session_id": session_id,
                    "status": results["overall_status"]
                }
            )

            return report_url

        except Exception as e:
            logger.error(f"Report generation error: {str(e)}")
            raise TestResultError(f"Failed to generate test report: {str(e)}")

    async def _generate_pdf_report(self, report_data: Dict[str, Any]) -> bytes:
        """Generate PDF report with test results and visualizations."""
        try:
            buffer = BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=letter)
            story = []
            styles = getSampleStyleSheet()
            
            # Add header
            story.append(Paragraph(
                f"Test Report - Session {report_data['session_info']['_id']}",
                styles['Heading1']
            ))
            story.append(Paragraph(
                f"Generated: {report_data['generated_at']}",
                styles['Normal']
            ))
            
            # Add session info
            session_data = [
                ["Vehicle ID", str(report_data['session_info']['vehicle_id'])],
                ["Test Center", str(report_data['session_info']['center_id'])],
                ["Status", report_data['test_results']['overall_status'].upper()],
                ["Completion Time", str(report_data['test_results']['completion_time'])]
            ]
            
            session_table = Table(session_data)
            session_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 14),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 12),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            story.append(session_table)
            
            # Add test results
            for test_type, results in report_data['test_results']['test_results'].items():
                story.append(Paragraph(f"\n{test_type.upper()} Results", styles['Heading2']))
                
                result_data = []
                for key, value in results.items():
                    if key != 'measurements':
                        result_data.append([key.replace('_', ' ').title(), str(value)])
                
                result_table = Table(result_data)
                result_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, -1), colors.lightgrey),
                    ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 0), (-1, -1), 10),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black)
                ]))
                story.append(result_table)
            
            doc.build(story)
            return buffer.getvalue()
            
        except Exception as e:
            logger.error(f"PDF generation error: {str(e)}")
            raise TestResultError(f"Failed to generate PDF report: {str(e)}")

    async def _send_result_notifications(
        self,
        session_id: str,
        status: str,
        report_url: str
    ) -> None:
        """Send test result notifications to relevant parties."""
        try:
            session_data = await self._get_test_session_data(session_id)
            
            # Notify vehicle owner
            await notification_service.send_notification(
                user_id=str(session_data["vehicle_owner_id"]),
                title="Vehicle Test Results Available",
                message=f"Your vehicle test has been completed. Status: {status}",
                data={
                    "session_id": session_id,
                    "status": status,
                    "report_url": report_url
                }
            )

            # Notify ATS center
            await notification_service.send_notification(
                user_id=str(session_data["center_id"]),
                title="Test Session Completed",
                message=f"Test session {session_id} has been completed",
                data={
                    "session_id": session_id,
                    "status": status
                }
            )

            # If test failed, notify RTO officer
            if status == "failed":
                await notification_service.send_notification(
                    user_id=str(session_data["rto_officer_id"]),
                    title="Failed Test Result",
                    message=f"Vehicle test failed for session {session_id}",
                    data={
                        "session_id": session_id,
                        "report_url": report_url
                    }
                )

        except Exception as e:
            logger.error(f"Notification error: {str(e)}")
            # Don't raise error as notifications are non-critical

    async def _update_session_status(
        self,
        session_id: str,
        status: str,
        report_url: str,
        db_session: Any
    ) -> None:
        """Update test session status with results."""
        try:
            await db_manager.execute_query(
                collection="test_sessions",
                operation="update_one",
                query={
                    "_id": ObjectId(session_id)
                },
                update={
                    "$set": {
                        "status": "completed",
                        "result_status": status,
                        "report_url": report_url,
                        "completed_at": datetime.utcnow()
                    }
                },
                session=db_session
            )
        except Exception as e:
            logger.error(f"Status update error: {str(e)}")
            raise TestResultError(f"Failed to update session status: {str(e)}")

    async def _get_test_session_data(self, session_id: str) -> Dict[str, Any]:
        """Retrieve test session details."""
        try:
            session_data = await db_manager.execute_query(
                collection="test_sessions",
                operation="find_one",
                query={"_id": ObjectId(session_id)}
            )
            
            if not session_data:
                raise TestResultError(f"Test session {session_id} not found")
                
            return session_data
            
        except Exception as e:
            logger.error(f"Session data retrieval error: {str(e)}")
            raise TestResultError(f"Failed to retrieve session data: {str(e)}")

    async def validate_test_data_completeness(
        self,
        test_data: Dict[str, Any]
    ) -> None:
        """Validate completeness of test data."""
        required_tests = {"speed_test", "brake_test", "headlight_test", "noise_test"}
        missing_tests = required_tests - set(test_data.keys())
        
        if missing_tests:
            raise TestResultError(f"Missing required tests: {', '.join(missing_tests)}")
        
        for test_type, data in test_data.items():
            if not data.get("measurements"):
                raise TestResultError(f"No measurements found for {test_type}")

# Initialize test results service with required interfaces
test_results_service = TestResultsService(
    test_service=test_service_instance,  # Import from test service module
    test_monitor=test_monitor_instance   # Import from test monitor module
)