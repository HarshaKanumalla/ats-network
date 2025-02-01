# backend/app/services/test/results_service.py

from datetime import datetime
from typing import Dict, Any, List, Optional
import logging
import json
from bson import ObjectId

from ...core.exceptions import TestResultError
from ...services.s3.s3_service import s3_service
from ...services.notification.notification_service import notification_service
from ...database import db_manager, database_transaction
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class TestResultService:
    def __init__(self):
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
        logger.info("Test result service initialized")

    async def process_test_results(
        self,
        session_id: str,
        test_data: Dict[str, Any],
        operator_id: str
    ) -> Dict[str, Any]:
        """Process and validate complete test results with comprehensive analysis."""
        async with database_transaction() as session:
            try:
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

# Initialize test result service
test_result_service = TestResultService()