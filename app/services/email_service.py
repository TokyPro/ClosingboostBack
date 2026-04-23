
import asyncio
import logging
from typing import Optional

import aiosmtplib
from pydantic_settings import BaseSettings

from ..models.core import OutreachMessage

logger = logging.getLogger(__name__)

class SMTPSettings(BaseSettings):
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    smtp_sender_email: str
    smtp_use_tls: bool = True # Default to using TLS

    class Config:
        env_prefix = "SMTP_" # Reads environment variables like SMTP_HOST, SMTP_PORT etc.

class EmailService:
    def __init__(self, settings: SMTPSettings):
        self.settings = settings

    async def send_email(
        self,
        to_email: str,
        subject: str,
        body: str,
        lead_tier: Optional[str] = None,
        outreach_message: Optional[OutreachMessage] = None # To update status later
    ) -> bool:
        """Sends an email to a single recipient."""
        message = aiosmtplib.Message(
            body=body,
            subject=subject,
            from_addr=self.settings.smtp_sender_email,
            to_addrs=[to_email],
        )
        
        # Optionally add custom headers based on lead tier for tracking/segmentation
        if lead_tier:
            message.add_header("X-Lead-Tier", lead_tier)
            
        # If an OutreachMessage object is provided, we can use its ID for potential future tracking
        if outreach_message:
            message.add_header("X-Outreach-ID", str(outreach_message.id))

        try:
            logger.info(f"Attempting to send email to {to_email} with subject: {subject}")
            async with aiosmtplib.SMTP(
                hostname=self.settings.smtp_host,
                port=self.settings.smtp_port,
                use_tls=self.settings.smtp_use_tls,
            ) as smtp_client:
                await smtp_client.login(
                    username=self.settings.smtp_user,
                    password=self.settings.smtp_password,
                )
                await smtp_client.sendmail(message)
            logger.info(f"Email sent successfully to {to_email}")
            return True
        except aiosmtplib.SMTPException as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            return False
        except Exception as e:
            logger.error(f"An unexpected error occurred while sending email to {to_email}: {e}")
            return False

# Example of how this service might be instantiated and used (e.g., in a FastAPI dependency or background task)
# async def get_email_service() -> EmailService:
#     settings = SMTPSettings()
#     return EmailService(settings)
