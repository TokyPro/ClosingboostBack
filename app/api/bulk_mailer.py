
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Dict
import datetime
import logging

from backend.app.database import get_db
from backend.app.services.agent_service import AgentService
from backend.app.services.email_service import EmailService, SMTPSettings
from backend.app.services.ai_service import AIIntelligenceService
from backend.app.repositories.lead_repository import LeadRepository
from backend.app.repositories.outreach_repository import OutreachRepository
from backend.app.models.core import OutreachMessage, Lead
from backend.app.services.lead_service import LeadService # Potentially useful for lead fetching by tier
# Assuming a basic user dependency exists, e.g., for authentication
# from backend.app.dependencies import get_current_user 

logger = logging.getLogger(__name__)

router = APIRouter()

# --- Dependency Functions ---

async def get_email_service() -> EmailService:
    """Dependency to get an instance of EmailService."""
    try:
        settings = SMTPSettings()
        # Basic validation for essential SMTP settings
        if not all([settings.smtp_host, settings.smtp_port, settings.smtp_user, settings.smtp_password, settings.smtp_sender_email]):
            raise ValueError("SMTP configuration is incomplete. Please set SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_SENDER_EMAIL.")
        return EmailService(settings)
    except Exception as e:
        logger.error(f"Failed to initialize EmailService: {e}")
        raise HTTPException(status_code=500, detail=f"Email service configuration error: {e}")

async def get_agent_service(db: AsyncSession = Depends(get_db)) -> AgentService:
    """Dependency to get an instance of AgentService."""
    # Initialize dependencies for AgentService
    ai_service = AIIntelligenceService() # Assuming AIIntelligenceService is stateless or initialized without complex dependencies
    # Note: A more robust DI pattern might inject these services directly.
    return AgentService(db=db, ai_service=ai_service)

async def get_lead_repository(db: AsyncSession = Depends(get_db)) -> LeadRepository:
    """Dependency to get an instance of LeadRepository."""
    return LeadRepository(db)

async def get_outreach_repository(db: AsyncSession = Depends(get_db)) -> OutreachRepository:
    """Dependency to get an instance of OutreachRepository."""
    return OutreachRepository(db)

# Placeholder for user authentication dependency if needed
# async def get_current_user(token: str = Depends(oauth2_scheme)) -> Dict:
#     # Replace with actual user lookup logic
#     return {"id": "dummy-user-id"}

# --- API Endpoint for Bulk Email Sending ---

@router.post("/send-bulk-emails", status_code=202, summary="Trigger bulk personalized email sending for a lead tier")
async def trigger_bulk_email_sending(
    tier: str = Query(..., description="Lead tier to target (cold, warm, hot)"),
    # current_user: dict = Depends(get_current_user), # Uncomment if authentication is required
    db: AsyncSession = Depends(get_db),
    agent_service: AgentService = Depends(get_agent_service),
    email_service: EmailService = Depends(get_email_service),
    lead_repo: LeadRepository = Depends(get_lead_repository),
    outreach_repo: OutreachRepository = Depends(get_outreach_repository)
):
    """
    Initiates the process of sending personalized bulk emails to leads of a specified tier.

    This endpoint will fetch leads, generate personalized messages using the AI agent,
    save them as drafts, and then attempt to send them via email.
    It performs synchronous batch processing. For large volumes, consider a dedicated background task system.

    Args:
        tier: The lead tier to target ('cold', 'warm', or 'hot').
        db: Database session dependency.
        agent_service: AgentService instance for message generation.
        email_service: EmailService instance for sending emails.
        lead_repo: LeadRepository instance for fetching leads.
        outreach_repo: OutreachRepository instance for managing messages.
        # current_user: Authenticated user information.
    """
    valid_tiers = ["cold", "warm", "hot"]
    if tier not in valid_tiers:
        raise HTTPException(status_code=400, detail=f"Invalid tier '{tier}'. Must be one of: {', '.join(valid_tiers)}")

    try:
        # Fetch leads for the specified tier
        # Note: get_by_tier might need to be adjusted if 'tier' is not directly stored or if 'status' is used instead.
        # Based on previous findings, 'tier' is a field in Lead model.
        leads_to_process = await lead_repo.get_by_tier(tier)
    except Exception as e:
        logger.error(f"Error fetching leads for tier '{tier}': {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve leads for processing.")

    if not leads_to_process:
        return {"message": f"No leads found for tier '{tier}' to process."}

    sent_count = 0
    failed_count = 0
    processed_lead_ids = []

    logger.info(f"Starting bulk email process for {len(leads_to_process)} leads in tier '{tier}'...")

    for lead in leads_to_process:
        processed_lead_ids.append(lead.id)
        message_id = None # Initialize message_id for error handling
        try:
            # 1. Generate message content and save draft using AgentService
            # AgentService.run_agent generates the message and saves it as a draft OutreachMessage.
            # It returns a dictionary including message_id, subject, message_content, tier.
            agent_result = await agent_service.run_agent(lead.id)

            if not agent_result or "message_id" not in agent_result:
                logger.error(f"Agent failed to generate message for lead {lead.id}. Skipping.")
                failed_count += 1
                continue
            
            message_id = agent_result["message_id"]
            subject = agent_result.get("subject", "No Subject Provided")
            message_body = agent_result.get("message_content", "")
            lead_tier_for_email = agent_result.get("tier", lead.tier) # Use tier from agent result if available, else fallback to lead's tier

            if not lead.contact_email:
                logger.warning(f"Lead {lead.id} ({lead.contact_name}) has no contact email. Skipping email sending.")
                # Update message status to 'skipped' or 'failed' if email cannot be sent due to missing info
                await outreach_repo.update_message_status(
                    msg_id=message_id,
                    status="failed", # Or a specific status like 'skipped_no_email'
                    failed_at=datetime.datetime.now(datetime.timezone.utc),
                    failure_reason="Missing contact email"
                )
                failed_count += 1
                continue

            # Retrieve the saved OutreachMessage draft
            outreach_message_draft = await outreach_repo.get_message_by_id(message_id)

            if not outreach_message_draft:
                logger.error(f"Could not retrieve generated draft message {message_id} for lead {lead.id} after generation. Skipping.")
                failed_count += 1
                continue

            # 2. Send the email using EmailService
            email_sent = await email_service.send_email(
                to_email=lead.contact_email,
                subject=subject,
                body=message_body,
                lead_tier=lead_tier_for_email,
                outreach_message=outreach_message_draft # Pass draft for potential header/tracking info
            )

            # 3. Update the OutreachMessage status based on send result
            if email_sent:
                await outreach_repo.update_message_status(
                    msg_id=message_id,
                    status="sent",
                    sent_at=datetime.datetime.now(datetime.timezone.utc)
                )
                sent_count += 1
            else:
                await outreach_repo.update_message_status(
                    msg_id=message_id,
                    status="failed",
                    failed_at=datetime.datetime.now(datetime.timezone.utc),
                    failure_reason="Email sending failed" # Placeholder, more detail might be logged by email_service
                )
                failed_count += 1

        except Exception as e:
            logger.error(f"Error processing lead {lead.id} for bulk email: {e}", exc_info=True)
            failed_count += 1
            # Ensure status is updated to failed if an error occurred during processing or sending
            if message_id: # If message was at least generated
                try:
                    await outreach_repo.update_message_status(
                        msg_id=message_id,
                        status="failed",
                        failed_at=datetime.datetime.now(datetime.timezone.utc),
                        failure_reason=f"Error during processing: {str(e)}"
                    )
                except Exception as update_e:
                    logger.error(f"Failed to update status to 'failed' for message {message_id} after error: {update_e}")

    logger.info(f"Bulk email process completed for tier '{tier}'.")
    return {
        "message": f"Bulk email process initiated for tier '{tier}'.",
        "targets": {
            "tier": tier,
            "total_leads_targeted": len(leads_to_process),
            "lead_ids_processed": processed_lead_ids
        },
        "results": {
            "emails_sent": sent_count,
            "emails_failed": failed_count,
            "emails_skipped_no_email": len([lid for lid in processed_lead_ids if lead_repo.get_by_id(lid).contact_email is None]) # Placeholder logic
        }
    }

# --- Modifications to OutreachRepository needed ---
# Add `get_message_by_id` method to OutreachRepository.py
# Add `failure_reason` field to OutreachMessage model and update_message_status method if desired for more detail.
# Ensure SMTPSettings correctly loads from environment variables.
# Ensure get_current_user dependency is implemented if authentication is needed.
# The AgentService.run_agent method implicitly updates lead.outreach_attempts and lead.last_outreach_at.
# This behavior is acceptable.
