# backend/app/services/report/service.py

"""
Service for generating comprehensive reports including test results,
center performance, and system analytics.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import logging
from bson import ObjectId
import jinja2
import pdfkit

from ...core.exceptions import ReportError
from ...services.s3 import s3_service
from ...database import get_database
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class ReportService:
    """Service for generating and managing various types of reports."""
    
    def __init__(self):
        """Initialize report service with template engine."""
        self.template_loader = jinja2.FileSystemLoader('app/templates/reports')
        self.template_env = jinja2.Environment(loader=self.template_loader)
        self.db = None
        logger.info("Report service initialized")

    async def generate_test_report(
        self,
        session_id: str
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
                        "localField": "atsCenterId",
                        "foreignField": "_id",
                        "as": "center"
                    }
                }
            ]
            
            result = await db.testSessions.aggregate(pipeline).to_list(1)
            if not result:
                raise ReportError("Test session not found")
            
            session_data = result[0]
            
            # Prepare report data
            report_data = {
                "session_code": session_data["sessionCode"],
                "test_date": session_data["testDate"],
                "vehicle": session_data["vehicle"][0],
                "center": session_data["center"][0],
                "test_results": session_data["testResults"],
                "final_results": session_data.get("finalResults", {}),
                "generated_at": datetime.utcnow()
            }
            
            # Generate HTML report
            template = self.template_env.get_template('test_report.html')
            html_content = template.render(**report_data)
            
            # Convert to PDF
            pdf_content = await self._convert_to_pdf(html_content)
            
            # Store in S3
            report_url = await s3_service.upload_document(
                file=pdf_content,
                folder=f"reports/tests/{session_id}",
                filename=f"test_report_{session_data['sessionCode']}.pdf",
                content_type="application/pdf"
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
            
            logger.info(f"Generated test report for session: {session_id}")
            return report_url
            
        except Exception as e:
            logger.error(f"Test report generation error: {str(e)}")
            raise ReportError("Failed to generate test report")

    async def generate_center_performance_report(
        self,
        center_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> str:
        """Generate center performance analysis report."""
        try:
            db = await get_database()
            
            # Get center data
            center = await db.centers.find_one({"_id": ObjectId(center_id)})
            if not center:
                raise ReportError("Center not found")
            
            # Get test statistics
            pipeline = [
                {
                    "$match": {
                        "atsCenterId": ObjectId(center_id),
                        "testDate": {
                            "$gte": start_date,
                            "$lte": end_date
                        }
                    }
                },
                {
                    "$group": {
                        "_id": None,
                        "total_tests": {"$sum": 1},
                        "passed_tests": {
                            "$sum": {
                                "$cond": [
                                    {"$eq": ["$status", "passed"]},
                                    1,
                                    0
                                ]
                            }
                        },
                        "failed_tests": {
                            "$sum": {
                                "$cond": [
                                    {"$eq": ["$status", "failed"]},
                                    1,
                                    0
                                ]
                            }
                        },
                        "average_duration": {"$avg": "$duration"}
                    }
                }
            ]
            
            stats = await db.testSessions.aggregate(pipeline).to_list(1)
            
            # Prepare report data
            report_data = {
                "center": center,
                "statistics": stats[0] if stats else {},
                "period": {
                    "start_date": start_date,
                    "end_date": end_date
                },
                "generated_at": datetime.utcnow()
            }
            
            # Generate report
            template = self.template_env.get_template('center_report.html')
            html_content = template.render(**report_data)
            
            # Convert and store
            pdf_content = await self._convert_to_pdf(html_content)
            report_url = await s3_service.upload_document(
                file=pdf_content,
                folder=f"reports/centers/{center_id}",
                filename=f"performance_report_{start_date.strftime('%Y%m%d')}.pdf",
                content_type="application/pdf"
            )
            
            logger.info(f"Generated performance report for center: {center_id}")
            return report_url
            
        except Exception as e:
            logger.error(f"Center report generation error: {str(e)}")
            raise ReportError("Failed to generate center performance report")

    async def generate_system_analytics_report(
        self,
        report_type: str,
        parameters: Dict[str, Any]
    ) -> str:
        """Generate system-wide analytics report."""
        try:
            # Implementation for system analytics report
            pass
            
        except Exception as e:
            logger.error(f"Analytics report generation error: {str(e)}")
            raise ReportError("Failed to generate analytics report")

    async def _convert_to_pdf(self, html_content: str) -> bytes:
        """Convert HTML content to PDF."""
        try:
            options = {
                'page-size': 'A4',
                'margin-top': '0.75in',
                'margin-right': '0.75in',
                'margin-bottom': '0.75in',
                'margin-left': '0.75in',
                'encoding': "UTF-8"
            }
            
            return pdfkit.from_string(html_content, False, options=options)
            
        except Exception as e:
            logger.error(f"PDF conversion error: {str(e)}")
            raise ReportError("Failed to convert report to PDF")

# Initialize report service
report_service = ReportService()