# backend/app/services/email/service.py

from typing import Dict, Any, Optional, List
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import aiosmtplib
import jinja2
import aiofiles
from pathlib import Path

from ...core.exceptions import EmailError
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class EmailService:
    """Enhanced service for handling all system email communications."""
    
    def __init__(self):
        """Initialize email service with templates and configuration."""
        self.template_loader = jinja2.FileSystemLoader(
            searchpath=str(Path(__file__).parent.parent / "templates" / "email")
        )
        self.template_env = jinja2.Environment(
            loader=self.template_loader,
            autoescape=True
        )

        # Email configuration
        self.smtp_config = {
            'hostname': settings.MAIL_SERVER,
            'port': settings.MAIL_PORT,
            'username': settings.MAIL_USERNAME,
            'password': settings.MAIL_PASSWORD,
            'use_tls': settings.MAIL_TLS,
            'timeout': 30
        }

        # Retry configuration
        self.retry_attempts = 3
        self.retry_delay = 5  # seconds

        logger.info("Email service initialized with enhanced configuration")

    async def send_registration_pending(
        self,
        email: str,
        name: str,
        center_details: Dict[str, Any]
    ) -> None:
        """Send registration pending notification with enhanced tracking."""
        try:
            template = self.template_env.get_template("registration_pending.html")
            html_content = template.render(
                name=name,
                email=email,
                ats_center=center_details.get('name', ''),
                address=center_details.get('address', ''),
                timestamp=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            )

            subject = "ATS Network Registration Pending Verification"
            await self._send_email_with_retry(
                recipient=email,
                subject=subject,
                html_content=html_content,
                metadata={
                    "email_type": "registration_pending",
                    "center_name": center_details.get('name')
                }
            )

            logger.info(f"Sent registration pending email to: {email}")

        except Exception as e:
            logger.error(f"Registration pending email error: {str(e)}")
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
            template = self.template_env.get_template("registration_approved.html")
            html_content = template.render(
                name=name,
                email=email,
                role=role,
                center_details=center_details,
                login_url=settings.FRONTEND_URL,
                timestamp=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            )

            subject = "ATS Network Registration Approved"
            await self._send_email_with_retry(
                recipient=email,
                subject=subject,
                html_content=html_content,
                metadata={
                    "email_type": "registration_approved",
                    "role": role
                }
            )

            logger.info(f"Sent registration approval email to: {email}")

        except Exception as e:
            logger.error(f"Registration approval email error: {str(e)}")
            raise EmailError(f"Failed to send approval email: {str(e)}")

    async def send_password_reset(
        self,
        email: str,
        name: str,
        reset_token: str
    ) -> None:
        """Send password reset email with secure token."""
        try:
            template = self.template_env.get_template("password_reset.html")
            reset_link = f"{settings.FRONTEND_URL}/reset-password?token={reset_token}"
            
            html_content = template.render(
                name=name,
                reset_link=reset_link,
                expiry_hours=24,
                timestamp=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            )

            subject = "Password Reset Request"
            await self._send_email_with_retry(
                recipient=email,
                subject=subject,
                html_content=html_content,
                metadata={
                    "email_type": "password_reset",
                    "token_expiry": "24_hours"
                }
            )

            logger.info(f"Sent password reset email to: {email}")

        except Exception as e:
            logger.error(f"Password reset email error: {str(e)}")
            raise EmailError(f"Failed to send password reset email: {str(e)}")

    async def send_role_update(
        self,
        email: str,
        name: str,
        new_role: str
    ) -> None:
        """Send role update notification."""
        try:
            template = self.template_env.get_template("role_update.html")
            html_content = template.render(
                name=name,
                role=new_role,
                effective_date=datetime.utcnow().strftime("%Y-%m-%d"),
                timestamp=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            )

            subject = "Role Access Update - ATS Network"
            await self._send_email_with_retry(
                recipient=email,
                subject=subject,
                html_content=html_content,
                metadata={
                    "email_type": "role_update",
                    "new_role": new_role
                }
            )

            logger.info(f"Sent role update email to: {email}")

        except Exception as e:
            logger.error(f"Role update email error: {str(e)}")
            raise EmailError(f"Failed to send role update email: {str(e)}")

    async def _send_email_with_retry(
        self,
        recipient: str,
        subject: str,
        html_content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Send email with retry mechanism and logging."""
        attempts = 0
        while attempts < self.retry_attempts:
            try:
                message = MIMEMultipart('alternative')
                message['Subject'] = subject
                message['From'] = settings.MAIL_FROM
                message['To'] = recipient

                html_part = MIMEText(html_content, 'html')
                message.attach(html_part)

                async with aiosmtplib.SMTP(
                    hostname=self.smtp_config['hostname'],
                    port=self.smtp_config['port'],
                    use_tls=self.smtp_config['use_tls'],
                    username=self.smtp_config['username'],
                    password=self.smtp_config['password'],
                    timeout=self.smtp_config['timeout']
                ) as smtp:
                    await smtp.send_message(message)

                # Log successful send
                await self._log_email_success(
                    recipient=recipient,
                    subject=subject,
                    metadata=metadata
                )
                return

            except Exception as e:
                attempts += 1
                if attempts == self.retry_attempts:
                    await self._log_email_failure(
                        recipient=recipient,
                        subject=subject,
                        error=str(e)
                    )
                    raise EmailError(f"Failed to send email after {attempts} attempts")
                await asyncio.sleep(self.retry_delay)

    async def _log_email_success(
        self,
        recipient: str,
        subject: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log successful email delivery."""
        try:
            log_entry = {
                "recipient": recipient,
                "subject": subject,
                "metadata": metadata,
                "status": "sent",
                "timestamp": datetime.utcnow()
            }
            # Implementation for logging to database or monitoring system
            pass
        except Exception as e:
            logger.error(f"Email logging error: {str(e)}")

    async def _log_email_failure(
        self,
        recipient: str,
        subject: str,
        error: str
    ) -> None:
        """Log failed email delivery attempt."""
        try:
            log_entry = {
                "recipient": recipient,
                "subject": subject,
                "error": error,
                "status": "failed",
                "timestamp": datetime.utcnow()
            }
            # Implementation for logging to database or monitoring system
            pass
        except Exception as e:
            logger.error(f"Email failure logging error: {str(e)}")

# Initialize email service
email_service = EmailService()