from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import logging
import jinja2
from bson import ObjectId
import pandas as pd
import pdfkit
import json

from ...core.exceptions import ReportError
from ...services.s3 import s3_service
from ...services.notification import notification_service
from ...database import get_database, database_transaction
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class ReportService:
    """Enhanced service for generating comprehensive system reports."""
    
    def __init__(self):
        """Initialize report service with enhanced capabilities."""
        self.db = None
        
        # Initialize template engine
        self.template_loader = jinja2.FileSystemLoader('app/templates/reports')
        self.template_env = jinja2.Environment(
            loader=self.template_loader,
            autoescape=True
        )
        
        # Report configurations
        self.report_types = {
            "test_report": {
                "template": "test_report.html",
                "processors": ["_process_test_data"],
                "required_data": ["test_session", "vehicle_info"],
                "formats": ["pdf", "html"]
            },
            "center_performance": {
                "template": "center_performance.html",
                "processors": ["_process_center_metrics"],
                "required_data": ["center_info", "test_statistics"],
                "formats": ["pdf", "excel"]
            },
            "compliance_report": {
                "template": "compliance_report.html",
                "processors": ["_process_compliance_data"],
                "required_data": ["audit_logs", "test_records"],
                "formats": ["pdf"]
            }
        }
        
        # PDF generation settings
        self.pdf_options = {
            'page-size': 'A4',
            'margin-top': '0.75in',
            'margin-right': '0.75in',
            'margin-bottom': '0.75in',
            'margin-left': '0.75in',
            'encoding': "UTF-8",
            'custom-header': [
                ('Accept-Encoding', 'gzip')
            ]
        }
        
        logger.info("Report service initialized")

    async def generate_test_report(
        self,
        session_id: str,
        report_format: str = "pdf"
    ) -> str:
        """Generate detailed test report with results and analysis."""
        try:
            db = await get_database()
            
            # Get test session data with related information
            pipeline = [
                {"$match": {"_id": ObjectId(session_id)}},
                {
                    "$lookup": {
                        "from": "vehicles",
                        "localField": "vehicleId",
                        "foreignField": "_id",
                        "as": "vehicle"
                    }
                },
                {
                    "$lookup": {
                        "from": "centers",
                        "localField": "centerId",
                        "foreignField": "_id",
                        "as": "center"
                    }
                }
            ]
            
            result = await db.testSessions.aggregate(pipeline).to_list(1)
            if not result:
                raise ReportError("Test session not found")
            
            session_data = result[0]
            
            # Process test data
            report_data = await self._process_test_data(session_data)
            
            # Generate report content
            if report_format == "pdf":
                report_content = await self._generate_pdf_report(
                    "test_report",
                    report_data
                )
            elif report_format == "html":
                report_content = await self._generate_html_report(
                    "test_report",
                    report_data
                )
            else:
                raise ReportError(f"Unsupported report format: {report_format}")
            
            # Store report in S3
            report_url = await s3_service.upload_document(
                file=report_content,
                folder=f"reports/tests/{session_id}",
                filename=f"test_report_{session_data['sessionCode']}.{report_format}",
                content_type=f"application/{report_format}"
            )
            
            # Update session with report URL
            await db.testSessions.update_one(
                {"_id": ObjectId(session_id)},
                {
                    "$set": {
                        "reportUrl": report_url,
                        "updatedAt": datetime.utcnow()
                    }
                }
            )
            
            # Send notification
            await self._send_report_notification(session_data, report_url)
            
            logger.info(f"Generated test report for session: {session_id}")
            return report_url
            
        except Exception as e:
            logger.error(f"Report generation error: {str(e)}")
            raise ReportError(f"Failed to generate test report: {str(e)}")

    async def generate_center_performance_report(
        self,
        center_id: str,
        start_date: datetime,
        end_date: datetime,
        report_format: str = "pdf"
    ) -> str:
        """Generate center performance analysis report."""
        try:
            db = await get_database()
            
            # Get center data with test statistics
            pipeline = [
                {"$match": {"_id": ObjectId(center_id)}},
                {
                    "$lookup": {
                        "from": "testSessions",
                        "let": {"centerId": "$_id"},
                        "pipeline": [
                            {
                                "$match": {
                                    "$expr": {
                                        "$and": [
                                            {"$eq": ["$centerId", "$$centerId"]},
                                            {"$gte": ["$testDate", start_date]},
                                            {"$lte": ["$testDate", end_date]}
                                        ]
                                    }
                                }
                            }
                        ],
                        "as": "testSessions"
                    }
                }
            ]
            
            result = await db.centers.aggregate(pipeline).to_list(1)
            if not result:
                raise ReportError("Center not found")
                
            center_data = result[0]
            
            # Process center metrics
            report_data = await self._process_center_metrics(
                center_data,
                start_date,
                end_date
            )
            
            # Generate report
            if report_format == "pdf":
                report_content = await self._generate_pdf_report(
                    "center_performance",
                    report_data
                )
            elif report_format == "excel":
                report_content = await self._generate_excel_report(
                    "center_performance",
                    report_data
                )
            else:
                raise ReportError(f"Unsupported report format: {report_format}")
            
            # Store report
            filename = (
                f"performance_report_{center_data['centerCode']}_"
                f"{start_date.strftime('%Y%m%d')}.{report_format}"
            )
            report_url = await s3_service.upload_document(
                file=report_content,
                folder=f"reports/centers/{center_id}",
                filename=filename,
                content_type=f"application/{report_format}"
            )
            
            logger.info(f"Generated performance report for center: {center_id}")
            return report_url
            
        except Exception as e:
            logger.error(f"Performance report error: {str(e)}")
            raise ReportError("Failed to generate performance report")

    async def _process_test_data(self, session_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process test session data for report generation."""
        try:
            vehicle = session_data["vehicle"][0]
            center = session_data["center"][0]
            
            report_data = {
                "test_info": {
                    "session_code": session_data["sessionCode"],
                    "test_date": session_data["testDate"],
                    "start_time": session_data["startTime"],
                    "end_time": session_data["endTime"],
                    "duration": (
                        session_data["endTime"] - session_data["startTime"]
                    ).total_seconds() / 60
                },
                "vehicle_info": {
                    "registration_number": vehicle["registrationNumber"],
                    "vehicle_type": vehicle["vehicleType"],
                    "manufacturing_year": vehicle["manufacturingYear"],
                    "owner_details": vehicle["ownerInfo"]
                },
                "center_info": {
                    "name": center["centerName"],
                    "code": center["centerCode"],
                    "address": center["address"]
                },
                "test_results": {
                    "speed_test": self._process_speed_test_results(
                        session_data["testResults"].get("speedTest", {})
                    ),
                    "brake_test": self._process_brake_test_results(
                        session_data["testResults"].get("brakeTest", {})
                    ),
                    # Process other test results...
                },
                "final_result": session_data.get("finalResult", {}),
                "recommendations": session_data.get("recommendations", [])
            }
            
            return report_data
            
        except Exception as e:
            logger.error(f"Test data processing error: {str(e)}")
            raise ReportError("Failed to process test data")

    async def _generate_pdf_report(
        self,
        report_type: str,
        report_data: Dict[str, Any]
    ) -> bytes:
        """Generate PDF format report."""
        try:
            # Get report template
            template = self.template_env.get_template(
                self.report_types[report_type]["template"]
            )
            
            # Generate HTML content
            html_content = template.render(**report_data)
            
            # Convert to PDF
            pdf_content = pdfkit.from_string(
                html_content,
                False,
                options=self.pdf_options
            )
            
            return pdf_content
            
        except Exception as e:
            logger.error(f"PDF generation error: {str(e)}")
            raise ReportError("Failed to generate PDF report")

    async def _generate_excel_report(
        self,
        report_type: str,
        report_data: Dict[str, Any]
    ) -> bytes:
        """Generate Excel format report."""
        try:
            # Convert data to DataFrame
            df = pd.DataFrame([report_data])
            
            # Generate Excel file
            excel_buffer = pd.ExcelWriter("temp.xlsx", engine="xlsxwriter")
            df.to_excel(excel_buffer, index=False)
            excel_buffer.close()
            
            with open("temp.xlsx", "rb") as f:
                excel_content = f.read()
            
            return excel_content
            
        except Exception as e:
            logger.error(f"Excel generation error: {str(e)}")
            raise ReportError("Failed to generate Excel report")

    def _process_speed_test_results(
        self,
        speed_test: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process speed test results for reporting."""
        return {
            "max_speed": speed_test.get("maxSpeed"),
            "target_speed": speed_test.get("targetSpeed"),
            "actual_speed": speed_test.get("actualSpeed"),
            "deviation": speed_test.get("deviation"),
            "status": speed_test.get("status"),
            "timestamp": speed_test.get("timestamp")
        }

    def _process_brake_test_results(
        self,
        brake_test: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process brake test results for reporting."""
        return {
            "brake_force": brake_test.get("brakeForce"),
            "imbalance": brake_test.get("imbalance"),
            "efficiency": brake_test.get("efficiency"),
            "status": brake_test.get("status"),
            "timestamp": brake_test.get("timestamp")
        }

    async def _send_report_notification(
        self,
        session_data: Dict[str, Any],
        report_url: str
    ) -> None:
        """Send notification about report generation."""
        try:
            # Notify vehicle owner
            await notification_service.send_notification(
                user_id=str(session_data["vehicle"][0]["ownerInfo"]["userId"]),
                title="Test Report Available",
                message=(
                    f"Test report for vehicle "
                    f"{session_data['vehicle'][0]['registrationNumber']} "
                    "is now available"
                ),
                notification_type="report_ready",
                data={"report_url": report_url}
            )
            
            # Notify center
            await notification_service.send_notification(
                user_id=str(session_data["center"][0]["owner"]["userId"]),
                title="Test Report Generated",
                message=(
                    f"Test report for session {session_data['sessionCode']} "
                    "has been generated"
                ),
                notification_type="report_ready",
                data={"report_url": report_url}
            )
            
        except Exception as e:
            logger.error(f"Report notification error: {str(e)}")

# Initialize report service
report_service = ReportService()