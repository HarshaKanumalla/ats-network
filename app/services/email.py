"""Email service for managing all application email communications."""

from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
from fastapi import HTTPException
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from jinja2 import Environment, PackageLoader, select_autoescape
import aiosmtplib

from ..config import get_settings
from ..models.user import User, UserStatus

logger = logging.getLogger(__name__)
settings = get_settings()

class EmailService:
    """Manages email operations and template rendering."""

    def __init__(self):
        """Initialize email service with required configurations."""
        self.email_config = ConnectionConfig(
            MAIL_USERNAME=settings.mail_username,
            MAIL_PASSWORD=settings.mail_password,
            MAIL_FROM=settings.mail_from,
            MAIL_PORT=settings.mail_port,
            MAIL_SERVER=settings.mail_server,
            MAIL_FROM_NAME="ATS Network",
            MAIL_STARTTLS=True,
            MAIL_SSL_TLS=False,
            USE_CREDENTIALS=True,
            VALIDATE_CERTS=True
        )

        self.template_env = Environment(
            loader=PackageLoader('app', 'templates/email'),
            autoescape=select_autoescape(['html', 'xml'])
        )
        
        self.fastmail = FastMail(self.email_config)
        logger.info("Email service initialized successfully")

    async def send_email(
        self,
        recipients: List[str],
        subject: str,
        template_name: str,
        template_data: Dict[str, Any]
    ) -> bool:
        """Send an email using a template.

        Args:
            recipients: List of email addresses to send to
            subject: Email subject line
            template_name: Name of the template to use
            template_data: Data to populate the template

        Returns:
            Boolean indicating successful delivery
        """
        try:
            template = self.template_env.get_template(f"{template_name}.html")
            html_content = template.render(**template_data)

            message = MessageSchema(
                subject=subject,
                recipients=recipients,
                body=html_content,
                subtype="html"
            )

            await self.fastmail.send_message(message)
            logger.info(f"Email sent successfully to {recipients}")
            return True

        except Exception as e:
            logger.error(f"Error sending email: {str(e)}")
            return False

# Initialize email service instance
email_service = EmailService()

async def send_approval_email(user: User) -> bool:
    """Send an approval notification email to a user.

    Args:
        user: The user whose registration has been approved

    Returns:
        Boolean indicating whether the email was sent successfully
    """
    try:
        template_data = {
            "user_name": user.full_name,
            "login_link": f"{settings.frontend_url}/login"
        }

        return await email_service.send_email(
            recipients=[user.email],
            subject="ATS Network Registration Approved",
            template_name="approval_notification",
            template_data=template_data
        )

    except Exception as e:
        logger.error(f"Error sending approval email to {user.email}: {str(e)}")
        return False

async def send_rejection_email(user: User, reason: Optional[str] = None) -> bool:
    """Send a rejection notification email to a user.

    Args:
        user: The user whose registration has been rejected
        reason: Optional reason for the rejection

    Returns:
        Boolean indicating whether the email was sent successfully
    """
    try:
        template_data = {
            "user_name": user.full_name,
            "reason": reason
        }

        return await email_service.send_email(
            recipients=[user.email],
            subject="ATS Network Registration Status Update",
            template_name="rejection_notification",
            template_data=template_data
        )

    except Exception as e:
        logger.error(f"Error sending rejection email to {user.email}: {str(e)}")
        return False

async def send_verification_email(user: User, verification_token: str) -> bool:
    """Send an email verification link to a newly registered user.

    Args:
        user: The newly registered user
        verification_token: The token for email verification

    Returns:
        Boolean indicating whether the email was sent successfully
    """
    try:
        verification_link = f"{settings.frontend_url}/verify-email?token={verification_token}"
        template_data = {
            "user_name": user.full_name,
            "verification_link": verification_link,
            "expiry_hours": 24
        }

        return await email_service.send_email(
            recipients=[user.email],
            subject="Verify Your ATS Network Email",
            template_name="email_verification",
            template_data=template_data
        )

    except Exception as e:
        logger.error(f"Error sending verification email to {user.email}: {str(e)}")
        return False