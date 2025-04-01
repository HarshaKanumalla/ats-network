from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Union
import logging
from bson import ObjectId
import re
import magic
import hashlib
from tenacity import retry, stop_after_attempt, wait_exponential

from ...core.exceptions import VehicleError
from ...models.vehicle import Vehicle, VehicleCreate, VehicleUpdate
from ...services.s3 import s3_service
from ...services.notification import notification_service
from ...database import get_database, database_transaction
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class VehicleManagementService:
    """Enhanced service for managing vehicle operations and records."""
    
    def __init__(self):
        """Initialize vehicle management service."""
        self.db = None
        
        # Document verification settings
        self.document_types = {
            "registration": {
                "required": True,
                "expiry_check": True,
                "allowed_formats": ["pdf", "jpg", "png"],
                "max_size": 5 * 1024 * 1024  # 5MB
            },
            "insurance": {
                "required": True,
                "expiry_check": True,
                "allowed_formats": ["pdf"],
                "max_size": 5 * 1024 * 1024
            },
            "fitness": {
                "required": False,
                "expiry_check": True,
                "allowed_formats": ["pdf"],
                "max_size": 5 * 1024 * 1024
            }
        }
        
        # Test validity periods (in days)
        self.test_validity = {
            "commercial": 180,  # 6 months
            "private": 365,    # 1 year
            "transport": 90    # 3 months
        }

        # Rate limiting settings
        self.upload_limits = {
            "max_per_minute": 10,
            "max_per_hour": 100
        }

        # Valid state codes
        self.valid_states = {
            'MH', 'DL', 'KA', 'TN', 'AP', 'TS', 'GJ', 'HR', 'UP', 'MP',
            'KL', 'RJ', 'UK', 'PB', 'OR', 'BR', 'JH', 'WB', 'CG', 'GA'
        }
        
        logger.info("Vehicle management service initialized")

    def _validate_registration_number(self, reg_number: str) -> bool:
        """Validate vehicle registration number format."""
        try:
            # Format: XX00XX0000 or XX-00-XX-0000
            # X: letter, 0: digit
            pattern = r'^[A-Z]{2}[-\s]?\d{2}[-\s]?[A-Z]{1,2}[-\s]?\d{4}$'
            
            # Remove spaces and hyphens for validation
            cleaned = re.sub(r'[-\s]', '', reg_number.upper())
            
            # Check pattern
            if not re.match(pattern, reg_number.upper()):
                return False
            
            # Validate state code (first 2 letters)
            state_code = cleaned[:2]
            if state_code not in self.valid_states:
                return False
            
            # Validate RTO code (2 digits)
            rto_code = int(cleaned[2:4])
            if not (1 <= rto_code <= 99):
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Registration validation error: {str(e)}")
            return False

    def _validate_document_format(
        self,
        file_data: bytes,
        allowed_formats: List[str]
    ) -> bool:
        """Validate document format and size."""
        try:
            # Check file type using python-magic
            mime = magic.Magic(mime=True)
            file_type = mime.from_buffer(file_data)
            
            # Map MIME types to extensions
            mime_to_ext = {
                'application/pdf': 'pdf',
                'image/jpeg': 'jpg',
                'image/png': 'png'
            }
            
            detected_format = mime_to_ext.get(file_type)
            if not detected_format or detected_format not in allowed_formats:
                logger.warning(
                    f"Invalid format detected: {file_type}. "
                    f"Allowed: {allowed_formats}"
                )
                return False
            
            # Check file size
            doc_config = next(
                (cfg for cfg in self.document_types.values()
                 if detected_format in cfg["allowed_formats"]),
                None
            )
            
            if doc_config and len(file_data) > doc_config["max_size"]:
                logger.warning(
                    f"File size ({len(file_data)} bytes) exceeds "
                    f"limit ({doc_config['max_size']} bytes)"
                )
                return False
            
            # Calculate and store checksum
            checksum = hashlib.sha256(file_data).hexdigest()
            self.document_checksums[checksum] = datetime.utcnow()
            
            return True
            
        except Exception as e:
            logger.error(f"Document format validation error: {str(e)}")
            return False

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    async def _send_test_notifications(
        self,
        vehicle: Dict[str, Any],
        test_session: Dict[str, Any]
    ) -> None:
        """Send notifications for test completion with retry."""
        try:
            # Notify owner
            await notification_service.send_notification(
                recipient_id=vehicle["ownerInfo"]["email"],
                title="Vehicle Test Completed",
                message=(
                    f"Test for vehicle {vehicle['registrationNumber']} "
                    f"has been completed with status: {test_session['status']}"
                ),
                notification_type="test_completion",
                data={
                    "test_session_id": str(test_session["_id"]),
                    "status": test_session["status"],
                    "next_test_due": vehicle["nextTestDue"].isoformat()
                }
            )
            
            # Notify center
            await notification_service.send_notification(
                recipient_id=str(test_session["atsCenterId"]),
                title="Test Session Completed",
                message=(
                    f"Test session for vehicle {vehicle['registrationNumber']} "
                    "has been recorded"
                ),
                notification_type="center_notification",
                data={
                    "test_session_id": str(test_session["_id"]),
                    "vehicle_id": str(vehicle["_id"])
                }
            )
            
            # Send status-specific notifications
            if test_session["status"] == "failed":
                await notification_service.send_notification(
                    recipient_id=vehicle["ownerInfo"]["email"],
                    title="Test Failed - Action Required",
                    message=(
                        f"Your vehicle {vehicle['registrationNumber']} "
                        "failed the test. Please schedule a retest."
                    ),
                    notification_type="test_failed",
                    data={
                        "test_session_id": str(test_session["_id"]),
                        "failure_reasons": test_session.get("failureReasons", []),
                        "retest_window": (
                            datetime.utcnow() + timedelta(days=30)
                        ).isoformat()
                    }
                )
            elif test_session["status"] == "passed":
                await self._generate_test_certificate(vehicle, test_session)
            
            logger.info(
                f"Sent test notifications for vehicle: {vehicle['registrationNumber']}"
            )
            
        except Exception as e:
            logger.error(f"Test notification error: {str(e)}")
            raise  # Allow retry mechanism to handle the error

    async def _generate_test_certificate(
        self,
        vehicle: Dict[str, Any],
        test_session: Dict[str, Any]
    ) -> None:
        """Generate and store test certificate."""
        try:
            certificate_number = (
                f"ATS-{datetime.utcnow().strftime('%Y%m%d')}-"
                f"{vehicle['registrationNumber']}"
            )
            
            # Generate certificate data
            certificate_data = {
                "certificateNumber": certificate_number,
                "vehicleRegistration": vehicle["registrationNumber"],
                "testDate": test_session["testDate"],
                "validUntil": vehicle["nextTestDue"],
                "testResults": test_session["results"],
                "issuingCenter": str(test_session["atsCenterId"]),
                "issuedAt": datetime.utcnow()
            }
            
            # Store certificate
            db = await get_database()
            await db.testCertificates.insert_one(certificate_data)
            
            # Update test session
            await db.testSessions.update_one(
                {"_id": test_session["_id"]},
                {"$set": {"certificateNumber": certificate_number}}
            )
            
            # Generate PDF certificate
            certificate_url = await self._generate_certificate_pdf(
                certificate_data
            )
            
            # Update certificate with URL
            await db.testCertificates.update_one(
                {"certificateNumber": certificate_number},
                {"$set": {"certificateUrl": certificate_url}}
            )
            
            # Notify owner
            await notification_service.send_notification(
                recipient_id=vehicle["ownerInfo"]["email"],
                title="Test Certificate Generated",
                message=(
                    f"Test certificate for vehicle {vehicle['registrationNumber']} "
                    "is now available"
                ),
                notification_type="certificate_generated",
                data={
                    "certificate_number": certificate_number,
                    "certificate_url": certificate_url
                }
            )
            
        except Exception as e:
            logger.error(f"Certificate generation error: {str(e)}")
            raise VehicleError(f"Failed to generate certificate: {str(e)}")

    async def _generate_certificate_pdf(
        self,
        certificate_data: Dict[str, Any]
    ) -> str:
        """Generate PDF certificate and upload to S3."""
        try:
            # Generate PDF using template
            from reportlab.pdfgen import canvas
            import io
            
            buffer = io.BytesIO()
            c = canvas.Canvas(buffer)
            
            # Add certificate content
            c.drawString(100, 800, "Vehicle Test Certificate")
            c.drawString(100, 780, f"Certificate Number: {certificate_data['certificateNumber']}")
            c.drawString(100, 760, f"Vehicle: {certificate_data['vehicleRegistration']}")
            c.drawString(100, 740, f"Test Date: {certificate_data['testDate'].strftime('%Y-%m-%d')}")
            c.drawString(100, 720, f"Valid Until: {certificate_data['validUntil'].strftime('%Y-%m-%d')}")
            
            c.save()
            
            # Upload to S3
            pdf_data = buffer.getvalue()
            s3_key = (
                f"certificates/{certificate_data['vehicleRegistration']}/"
                f"{certificate_data['certificateNumber']}.pdf"
            )
            
            url = await s3_service.upload_file(
                pdf_data,
                s3_key,
                content_type='application/pdf'
            )
            
            return url
            
        except Exception as e:
            logger.error(f"PDF generation error: {str(e)}")
            raise VehicleError(f"Failed to generate PDF: {str(e)}")

    async def _schedule_document_checks(self, vehicle_id: str) -> None:
        """Schedule periodic document expiry checks."""
        try:
            db = await get_database()
            
            # Get vehicle documents
            vehicle = await db.vehicles.find_one({"_id": ObjectId(vehicle_id)})
            if not vehicle or "documentVerification" not in vehicle:
                return
            
            # Schedule checks for each document
            for doc_type, doc_info in vehicle["documentVerification"].items():
                if not self.document_types[doc_type]["expiry_check"]:
                    continue
                    
                if doc_info.get("expiryDate"):
                    expiry_date = doc_info["expiryDate"]
                    
                    # Schedule notifications at different intervals
                    notification_schedule = [
                        (30, "30 days before expiry"),
                        (15, "15 days before expiry"),
                        (7, "7 days before expiry"),
                        (1, "1 day before expiry")
                    ]
                    
                    for days, message in notification_schedule:
                        notification_date = expiry_date - timedelta(days=days)
                        if notification_date > datetime.utcnow():
                            await notification_service.schedule_notification(
                                recipient_id=vehicle["ownerInfo"]["email"],
                                title=f"Document Expiry Reminder: {doc_type}",
                                message=(
                                    f"Your {doc_type} for vehicle "
                                    f"{vehicle['registrationNumber']} "
                                    f"will expire in {days} days"
                                ),
                                notification_type="document_expiry",
                                scheduled_time=notification_date,
                                metadata={
                                    "vehicle_id": str(vehicle["_id"]),
                                    "document_type": doc_type,
                                    "days_to_expiry": days
                                }
                            )
            
            await self._update_check_schedule(vehicle_id)
            logger.info(f"Scheduled document checks for vehicle: {vehicle_id}")
            
        except Exception as e:
            logger.error(f"Document check scheduling error: {str(e)}")

    async def _update_check_schedule(self, vehicle_id: str) -> None:
        """Update document check schedule in database."""
        try:
            db = await get_database()
            await db.vehicles.update_one(
                {"_id": ObjectId(vehicle_id)},
                {
                    "$set": {
                        "lastCheckSchedule": datetime.utcnow(),
                        "nextCheckDue": datetime.utcnow() + timedelta(days=1)
                    }
                }
            )
        except Exception as e:
            logger.error(f"Check schedule update error: {str(e)}")

# Initialize vehicle management service
vehicle_service = VehicleManagementService()