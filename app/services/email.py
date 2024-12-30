# backend/app/services/email.py
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
from fastapi import HTTPException
import logging
from datetime import datetime
from typing import List, Dict, Any
from ..config import get_settings
from ..models.user import User, UserStatus

# Set up logging
logger = logging.getLogger(__name__)

# Get settings
settings = get_settings()

# System Info
SYSTEM_INFO = {
    "last_updated": "2024-12-19 18:16:02",
    "updated_by": "HarshaKanumalla"
}

# Email configuration
email_config = ConnectionConfig(
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

# Create FastMail instance
fastmail = FastMail(email_config)

async def send_email(
    recipients: List[str],
    subject: str,
    body: str,
    subtype: str = "html"
) -> bool:
    """Generic function to send email."""
    try:
        message = MessageSchema(
            subject=subject,
            recipients=recipients,
            body=body,
            subtype=subtype
        )
        await fastmail.send_message(message)
        logger.info(f"Email sent successfully to {recipients}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {recipients}: {str(e)}")
        return False

async def send_verification_email(email: str, token: str) -> bool:
    """Send verification email to user."""
    try:
        verification_link = f"{settings.frontend_url}/verify-email?token={token}"
        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif;">
                <h2>Verify Your ATS Network Account</h2>
                <p>Please click the following link to verify your email:</p>
                <p><a href="{verification_link}">{verification_link}</a></p>
                <p>This link will expire in 24 hours.</p>
                <p>If you did not create this account, please ignore this email.</p>
                <p>Best regards,<br>ATS Network Team</p>
            </body>
        </html>
        """
        return await send_email(
            recipients=[email],
            subject="Verify Your ATS Network Account",
            body=html_content
        )
    except Exception as e:
        logger.error(f"Error sending verification email: {str(e)}")
        return False

async def send_admin_notification(user_data: Dict[str, Any]) -> bool:
    """Send notification to admin about new registration."""
    try:
        action_link = f"{settings.frontend_url}/admin/users/{user_data.get('id', '')}"
        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif;">
                <h2>New User Registration</h2>
                <p>A new user has registered with the following details:</p>
                <table style="border-collapse: collapse; width: 100%;">
                    <tr>
                        <td style="padding: 8px; border: 1px solid #ddd;"><strong>Name</strong></td>
                        <td style="padding: 8px; border: 1px solid #ddd;">{user_data.get('full_name', 'N/A')}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border: 1px solid #ddd;"><strong>Email</strong></td>
                        <td style="padding: 8px; border: 1px solid #ddd;">{user_data.get('email', 'N/A')}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border: 1px solid #ddd;"><strong>ATS Address</strong></td>
                        <td style="padding: 8px; border: 1px solid #ddd;">{user_data.get('ats_address', 'N/A')}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border: 1px solid #ddd;"><strong>City</strong></td>
                        <td style="padding: 8px; border: 1px solid #ddd;">{user_data.get('city', 'N/A')}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border: 1px solid #ddd;"><strong>District</strong></td>
                        <td style="padding: 8px; border: 1px solid #ddd;">{user_data.get('district', 'N/A')}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border: 1px solid #ddd;"><strong>State</strong></td>
                        <td style="padding: 8px; border: 1px solid #ddd;">{user_data.get('state', 'N/A')}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border: 1px solid #ddd;"><strong>PIN Code</strong></td>
                        <td style="padding: 8px; border: 1px solid #ddd;">{user_data.get('pin_code', 'N/A')}</td>
                    </tr>
                </table>
                <p>Please review and take action on this registration:</p>
                <p><a href="{action_link}">Review Registration</a></p>
                <p>Timestamp: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
            </body>
        </html>
        """
        return await send_email(
            recipients=[settings.admin_email],
            subject="New User Registration - ATS Network",
            body=html_content
        )
    except Exception as e:
        logger.error(f"Error sending admin notification: {str(e)}")
        return False

async def send_registration_confirmation(user_data: Dict[str, Any]) -> bool:
    """Send registration confirmation to user."""
    try:
        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif;">
                <h2>Welcome to ATS Network</h2>
                <p>Dear {user_data.get('full_name', '')},</p>
                <p>Thank you for registering with ATS Network. Your registration is being reviewed by our admin team.</p>
                <p>Registration Details:</p>
                <ul>
                    <li>Email: {user_data.get('email')}</li>
                    <li>ATS Address: {user_data.get('ats_address')}</li>
                    <li>City: {user_data.get('city')}</li>
                    <li>Status: Pending Review</li>
                </ul>
                <p>You will receive another email once your registration is approved.</p>
                <p>Best regards,<br>ATS Network Team</p>
            </body>
        </html>
        """
        return await send_email(
            recipients=[user_data['email']],
            subject="Welcome to ATS Network",
            body=html_content
        )
    except Exception as e:
        logger.error(f"Error sending registration confirmation: {str(e)}")
        return False

async def send_approval_email(user: User) -> bool:
    """Send approval email to user."""
    try:
        login_link = f"{settings.frontend_url}/login"
        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif;">
                <h2>ATS Network Registration Approved</h2>
                <p>Dear {user.full_name},</p>
                <p>Congratulations! Your registration for ATS Network has been approved.</p>
                <p>You can now <a href="{login_link}">log in to your account</a> using your registered email and password.</p>
                <p>Account Details:</p>
                <ul>
                    <li>Email: {user.email}</li>
                    <li>ATS Address: {user.ats_address}</li>
                    <li>Status: Approved</li>
                </ul>
                <p>If you have any questions or need assistance, please don't hesitate to contact our support team.</p>
                <p>Best regards,<br>ATS Network Team</p>
            </body>
        </html>
        """
        return await send_email(
            recipients=[user.email],
            subject="ATS Network Registration Approved",
            body=html_content
        )
    except Exception as e:
        logger.error(f"Error sending approval email: {str(e)}")
        return False

async def send_rejection_email(user: User, reason: str) -> bool:
    """Send rejection email to user."""
    try:
        support_email = settings.support_email or settings.admin_email
        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif;">
                <h2>ATS Network Registration Status</h2>
                <p>Dear {user.full_name},</p>
                <p>We regret to inform you that your registration for ATS Network could not be approved at this time.</p>
                <p><strong>Reason:</strong> {reason}</p>
                <p>If you believe this is an error or would like to provide additional information, 
                   please contact our support team at <a href="mailto:{support_email}">{support_email}</a>.</p>
                <p>You may submit a new registration after addressing the concerns mentioned above.</p>
                <p>Best regards,<br>ATS Network Team</p>
            </body>
        </html>
        """
        return await send_email(
            recipients=[user.email],
            subject="ATS Network Registration Status",
            body=html_content
        )
    except Exception as e:
        logger.error(f"Error sending rejection email: {str(e)}")
        return False

# Export all email functions
__all__ = [
    'send_email',
    'send_verification_email',
    'send_admin_notification',
    'send_registration_confirmation',
    'send_approval_email',
    'send_rejection_email'
]