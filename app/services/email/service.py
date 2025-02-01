# backend/app/services/email/service.py

import boto3
from botocore.exceptions import ClientError
from typing import Optional, Dict, Any, List
import logging
from jinja2 import Environment, PackageLoader, select_autoescape
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import backoff
import json

from ...core.exceptions import EmailError
from ...database import db_manager
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class EmailService:
    def __init__(self):
        self.ses_client = boto3.client(
            'ses',
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_region
        )

        self.template_env = Environment(
            loader=PackageLoader('app', 'templates/email'),
            autoescape=select_autoescape(['html'])
        )

        self.retry_settings = {
            'max_attempts': 3,
            'initial_delay': 1,  # seconds
            'max_delay': 10,     # seconds
            'exponential_base': 2
        }

        self._verify_sender_email()
        logger.info("Email service initialized with enhanced retry mechanisms")

    async def send_registration_pending(
        self,
        email: str,
        name: str,
        center_details: Dict[str, Any]
    ) -> None:
        """Send registration pending notification with retry mechanism."""
        try:
            template = self.template_env.get_template('registration_pending.html')
            html_content = template.render(
                name=name,
                center_name=center_details['name'],
                center_address=center_details['address'],
                center_city=center_details['city'],
                timestamp=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            )

            await self._send_email_with_retry(
                recipient=email,
                subject="ATS Network Registration Pending Verification",
                html_content=html_content,
                email_type="registration_pending",
                metadata={
                    "user_name": name,
                    "center_name": center_details['name']
                }
            )

            logger.info(f"Sent registration pending email to: {email}")

        except Exception as e:
            logger.error(f"Failed to send registration pending email: {str(e)}")
            raise EmailError(f"Failed to send registration email: {str(e)}")

    async def send_registration_approved(
        self,
        email: str,
        name: str,
        role: str,
        center_details: Optional[Dict[str, Any]] = None
    ) -> None:
        """Send registration approval notification with login credentials."""
        try:
            template = self.template_env.get_template('registration_approved.html')
            html_content = template.render(
                name=name,
                role=role,
                center_details=center_details,
                login_url=settings.frontend_url,
                timestamp=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            )

            await self._send_email_with_retry(
                recipient=email,
                subject="ATS Network Registration Approved",
                html_content=html_content,
                email_type="registration_approved",
                metadata={
                    "user_name": name,
                    "role": role
                }
            )

            logger.info(f"Sent registration approval email to: {email}")

        except Exception as e:
            logger.error(f"Failed to send approval email: {str(e)}")
            raise EmailError(f"Failed to send approval email: {str(e)}")

    async def send_test_report(
        self,
        email: str,
        name: str,
        test_details: Dict[str, Any],
        report_url: str
    ) -> None:
        """Send test completion report with secure report access."""
        try:
            template = self.template_env.get_template('test_report.html')
            html_content = template.render(
                name=name,
                vehicle_number=test_details['vehicle_number'],
                test_date=test_details['test_date'],
                center_name=test_details['center_name'],
                test_status=test_details['status'],
                report_url=report_url,
                timestamp=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            )

            await self._send_email_with_retry(
                recipient=email,
                subject=f"Vehicle Test Report - {test_details['vehicle_number']}",
                html_content=html_content,
                email_type="test_report",
                metadata={
                    "vehicle_number": test_details['vehicle_number'],
                    "test_status": test_details['status']
                }
            )

            logger.info(f"Sent test report email for vehicle: {test_details['vehicle_number']}")

        except Exception as e:
            logger.error(f"Failed to send test report email: {str(e)}")
            raise EmailError(f"Failed to send test report: {str(e)}")

    @backoff.on_exception(
        backoff.expo,
        ClientError,
        max_tries=3,
        max_time=30
    )
    async def _send_email_with_retry(
        self,
        recipient: str,
        subject: str,
        html_content: str,
        email_type: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Send email with retry mechanism and proper error handling."""
        try:
            message = MIMEMultipart('alternative')
            message['Subject'] = subject
            message['From'] = settings.ses_sender_email
            message['To'] = recipient

            html_part = MIMEText(html_content, 'html')
            message.attach(html_part)

            delivery_attempt = 0
            max_attempts = self.retry_settings['max_attempts']

            while delivery_attempt < max_attempts:
                try:
                    response = await self.ses_client.send_raw_email(
                        Source=settings.ses_sender_email,
                        Destinations=[recipient],
                        RawMessage={
                            'Data': message.as_string()
                        }
                    )

                    await self._log_email_success(
                        recipient=recipient,
                        email_type=email_type,
                        metadata=metadata,
                        message_id=response['MessageId']
                    )
                    
                    return

                except ClientError as e:
                    delivery_attempt += 1
                    if delivery_attempt == max_attempts:
                        await self._log_email_failure(
                            recipient=recipient,
                            email_type=email_type,
                            error=str(e)
                        )
                        raise

                    await asyncio.sleep(
                        self.retry_settings['initial_delay'] * 
                        (self.retry_settings['exponential_base'] ** (delivery_attempt - 1))
                    )

        except Exception as e:
            logger.error(f"Email sending error: {str(e)}")
            raise EmailError(f"Failed to send email: {str(e)}")

    async def _log_email_success(
        self,
        recipient: str,
        email_type: str,
        metadata: Optional[Dict[str, Any]],
        message_id: str
    ) -> None:
        """Log successful email delivery."""
        try:
            await db_manager.execute_query(
                collection="email_logs",
                operation="insert_one",
                query={
                    "recipient": recipient,
                    "email_type": email_type,
                    "metadata": metadata,
                    "message_id": message_id,
                    "status": "delivered",
                    "sent_at": datetime.utcnow()
                }
            )
        except Exception as e:
            logger.error(f"Failed to log email success: {str(e)}")

    async def _log_email_failure(
        self,
        recipient: str,
        email_type: str,
        error: str
    ) -> None:
        """Log failed email delivery attempt."""
        try:
            await db_manager.execute_query(
                collection="email_logs",
                operation="insert_one",
                query={
                    "recipient": recipient,
                    "email_type": email_type,
                    "error": error,
                    "status": "failed",
                    "timestamp": datetime.utcnow()
                }
            )
        except Exception as e:
            logger.error(f"Failed to log email failure: {str(e)}")

    def _verify_sender_email(self) -> None:
        """Verify sender email address with AWS SES."""
        try:
            response = self.ses_client.get_identity_verification_attributes(
                Identities=[settings.ses_sender_email]
            )
            
            if settings.ses_sender_email not in response['VerificationAttributes']:
                self.ses_client.verify_email_identity(
                    EmailAddress=settings.ses_sender_email
                )
                logger.info(f"Verification email sent to {settings.ses_sender_email}")
                
        except Exception as e:
            logger.error(f"Email verification error: {str(e)}")
            raise EmailError("Failed to verify sender email")

# Initialize email service
email_service = EmailService()