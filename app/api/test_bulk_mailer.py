
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import datetime # Import datetime for time-based assertions

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

# Assuming your main app is in backend.app.main and you include routers there
# For testing purposes, we'll create a minimal app with the router included
# IMPORTANT: This assumes backend.app.main.app exists and the router is included.
# If not, you might need to create a minimal FastAPI app instance here for the TestClient.
# from backend.app.main import app # This needs to be available or mocked
# For now, let's create a minimal app instance and include the router
from backend.app.api import bulk_mailer # The new router
from backend.app.models.core import Lead, OutreachMessage # For type hinting and mocking
from backend.app.services.agent_service import AgentService # To mock
from backend.app.services.email_service import EmailService, SMTPSettings # To mock
from backend.app.repositories.lead_repository import LeadRepository # To mock
from backend.app.repositories.outreach_repository import OutreachRepository # To mock
from backend.app.database import get_db # To mock

# Create a minimal FastAPI app instance for testing and include the router
test_app = FastAPI()
test_app.include_router(bulk_mailer.router, prefix="/api/leads", tags=["Bulk Mailer"])

# --- Mock Dependencies ---

# Mock the get_db dependency
async def override_get_db():
    # In a real test suite, you'd use a test database or a mock session
    mock_db = AsyncMock(spec=AsyncSession)
    yield mock_db

# Mock AgentService
@pytest.fixture
def mock_agent_service():
    mock = AsyncMock(spec=AgentService)
    # Configure mock for successful message generation and draft saving
    # Ensure lead_id in return value matches the lead processed
    mock.run_agent.return_value = {
        "message_id": "mock-message-123",
        "subject": "Mock Subject",
        "message_content": "This is a mock email body.",
        "tier": "cold",
        "lead_id": "mock-lead-id-1" # Matches the first lead provided by mock_lead_repository
    }
    return mock

# Mock EmailService
@pytest.fixture
def mock_email_service():
    mock = AsyncMock(spec=EmailService)
    # Configure mock for successful email sending
    mock.send_email.return_value = True
    return mock

# Mock LeadRepository
@pytest.fixture
def mock_lead_repository():
    mock = AsyncMock(spec=LeadRepository)
    # Configure mock to return a list of leads for 'cold' tier
    mock.get_by_tier.return_value = [
        Lead(
            id="mock-lead-id-1",
            contact_email="test1@example.com",
            tier="cold",
            company_name="Company A",
            contact_name="Alice"
        ),
        Lead(
            id="mock-lead-id-2",
            contact_email=None, # Simulate a lead with no email
            tier="cold",
            company_name="Company B",
            contact_name="Bob"
        ),
    ]
    # Mock get_by_id for the error handling scenario in the loop if needed later
    mock.get_by_id.side_effect = lambda lead_id: next((l for l in mock.get_by_tier.return_value if l.id == lead_id), None)
    return mock

# Mock OutreachRepository
@pytest.fixture
def mock_outreach_repository():
    mock = AsyncMock(spec=OutreachRepository)
    # Mock create_message and get_message_by_id for the draft
    # Note: AgentService.run_agent returns a message_id, which get_message_by_id uses.
    # The created message needs to match the one retrieved.
    mock_draft_message = OutreachMessage(
        id="mock-message-123",
        lead_id="mock-lead-id-1",
        tier="cold",
        channel="email",
        subject="Mock Subject",
        message_content="This is a mock email body.",
        status="draft",
        score_before=50.0
    )
    mock.create_message.return_value = mock_draft_message # AgentService calls this
    mock.get_message_by_id.return_value = mock_draft_message # Endpoint calls this
    # Mock update_message_status to return something or just confirm it was called
    # We can make it return the updated mock_draft_message for consistency
    mock.update_message_status.return_value = mock_draft_message
    return mock

# --- Fixtures for Dependencies ---
@pytest.fixture(autouse=True)
def override_dependencies(
    mock_agent_service,
    mock_email_service,
    mock_lead_repository,
    mock_outreach_repository
):
    # Mock SMTPSettings to avoid actual SMTP connection attempts
    mock_smtp_settings = MagicMock(spec=SMTPSettings)
    mock_smtp_settings.smtp_host = "mock_host"
    mock_smtp_settings.smtp_port = 123
    mock_smtp_settings.smtp_user = "mock_user"
    mock_smtp_settings.smtp_password = "mock_password"
    mock_smtp_settings.smtp_sender_email = "mock_sender@example.com"
    mock_smtp_settings.smtp_use_tls = True

    # Patch dependencies used in the router
    # Use the test_app created above
    with patch('backend.app.services.email_service.SMTPSettings', return_value=mock_smtp_settings), 
         patch('backend.app.services.email_service.EmailService.__init__', return_value=None), 
         patch('backend.app.services.email_service.EmailService.__new__', return_value=mock_email_service): # Using __new__ to mock the instance

        # Patch dependencies used in the router functions
        test_app.dependency_overrides[get_db] = override_get_db
        test_app.dependency_overrides[bulk_mailer.get_agent_service] = lambda db=Depends(override_get_db): mock_agent_service
        test_app.dependency_overrides[bulk_mailer.get_email_service] = lambda: mock_email_service # EmailService is instantiated without DB
        test_app.dependency_overrides[bulk_mailer.get_lead_repository] = lambda db=Depends(override_get_db): mock_lead_repository
        test_app.dependency_overrides[bulk_mailer.get_outreach_repository] = lambda db=Depends(override_get_db): mock_outreach_repository

        # Patch datetime.datetime.now for time-based assertions
        with patch('backend.app.api.bulk_mailer.datetime.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime.datetime.now(datetime.timezone.utc)
            mock_datetime.timezone.utc = datetime.timezone.utc # Ensure timezone is available
            yield # Run the test

        # Clean up dependency overrides after the test
        test_app.dependency_overrides.clear()

# --- Test Cases ---

def test_trigger_bulk_email_sending_success(
    mock_agent_service,
    mock_email_service,
    mock_lead_repository,
    mock_outreach_repository
):
    """
    Test that bulk emails are sent successfully for a batch of cold leads.
    Covers:
    - Correct API response status (202 Accepted).
    - Processing of leads with email addresses.
    - Skipping of leads without email addresses.
    - Correct calls to AgentService, OutreachRepository, and EmailService.
    - Correct status updates for sent and failed/skipped messages.
    """
    client = TestClient(test_app) # Use the test_app instance

    # Make the API request
    response = client.post("/api/leads/send-bulk-emails?tier=cold")

    # --- Assertions ---
    assert response.status_code == 202 # Accepted

    response_data = response.json()
    assert response_data["message"] == "Bulk email process initiated for tier 'cold'."
    assert response_data["targets"]["tier"] == "cold"
    assert response_data["targets"]["total_leads_targeted"] == 2
    assert response_data["results"]["emails_sent"] == 1 # Only one lead (test1@example.com) has an email
    assert response_data["results"]["emails_failed"] == 0 # No actual sending failures mocked
    assert response_data["results"]["emails_skipped_no_email"] == 1 # One lead was skipped because of missing email

    # Verify mocks were called as expected
    mock_lead_repository.get_by_tier.assert_called_once_with("cold")
    # AgentService.run_agent is called for each lead in the loop. Since mock_lead_repository returns 2 leads,
    # and the first one has an email, AgentService should be called for the first lead.
    # If AgentService fails or the lead has no email, it might not be called for the second lead depending on logic flow.
    # Based on the current loop, it should be called for lead-1, then lead-2 will be skipped due to no email after agent call.
    # Let's adjust mock_agent_service.run_agent's side_effect to reflect this.
    
    # The current mock_agent_service.run_agent is a simple return_value.
    # The loop in bulk_mailer.py calls agent_service.run_agent(lead.id) for *each* lead.
    # So it should be called twice, but the test logic only asserts for the first lead's success.
    # Let's refine the mocks to handle multiple calls if needed, or adjust assertions based on the loop's behavior.
    # The current logic in bulk_mailer calls agent_service.run_agent, then retrieves the message, then sends.
    # It seems it tries to call agent_service.run_agent for *all* leads, even if they lack email.
    # Then it skips sending if email is missing. So, agent_service.run_agent should be called twice.
    
    mock_agent_service.run_agent.assert_any_call("mock-lead-id-1")
    mock_agent_service.run_agent.assert_any_call("mock-lead-id-2")
    assert mock_agent_service.run_agent.call_count == 2

    # create_message is called when agent_service.run_agent is successful
    mock_outreach_repository.create_message.assert_called_once() # Called for lead-1's agent result

    # get_message_by_id is called with the message_id returned by agent_service
    mock_outreach_repository.get_message_by_id.assert_called_once_with("mock-message-123")

    # email_service.send_email is called only for leads with emails
    mock_email_service.send_email.assert_called_once_with(
        to_email="test1@example.com",
        subject="Mock Subject",
        body="This is a mock email body.",
        lead_tier="cold",
        outreach_message=mock_outreach_repository.get_message_by_id.return_value # Check it was passed the draft
    )
    # update_message_status is called for both sent and failed/skipped
    assert mock_outreach_repository.update_message_status.call_count == 2 # Called for lead-1 (sent) and lead-2 (failed/skipped)

    # Verifying the status updates:
    # For lead-1 (sent):
    mock_outreach_repository.update_message_status.assert_any_call(
        msg_id="mock-message-123",
        status="sent",
        sent_at=pytest.approx(datetime.datetime.now(datetime.timezone.utc), abs=1)
    )
    # For lead-2 (skipped due to no email): The logic in bulk_mailer.py updates status to 'failed' with 'Missing contact email' reason.
    # To test this precisely, we'd need to mock agent_service.run_agent for the second lead too,
    # or mock lead_repo.get_by_id to see if it's called.
    # For now, let's assume the flow leads to an update_message_status call for lead-2.
    # The exact parameters depend on the failure reason logic.
    # Let's refine the mock_agent_service to return different results or mock the lead fetching directly.

    # --- Let's refine the mock_agent_service and the test logic ---
    # The current test logic in bulk_mailer.py calls agent_service.run_agent for *each* lead,
    # then checks if the lead has an email, then retrieves the message, then sends.
    # If email is missing, it updates status to 'failed' *before* trying to retrieve message.
    # So, agent_service.run_agent is called twice.
    # create_message is called twice.
    # get_message_by_id is called only if agent_service returns a message_id.
    # email_service.send_email is called only if email exists.
    # update_message_status is called for each lead processed.

    # Let's adjust the mocks and assertions to reflect this:
    # The existing mock_agent_service.run_agent.return_value is static.
    # We need it to return unique message_ids for each lead or handle it differently.

    # Simpler approach for now: Assert that *a* message was sent, and *a* failure occurred.
    # The count for skipped/failed should align with the lead data.

    # Re-evaluating based on the loop in bulk_mailer.py:
    # 1. Loop for lead 1 (has email): agent_service.run_agent -> create_message -> get_message_by_id -> send_email -> update_message_status (sent)
    # 2. Loop for lead 2 (no email): agent_service.run_agent -> FAILS IF AGENT ASSUMES EMAIL EXISTS (or handles gracefully) -> IF EMAIL MISSING, updates status to 'failed' early.
    # The current mock_agent_service.run_agent *always* returns a result with message_id.
    # The logic `if not lead.contact_email:` happens *after* agent_result is obtained.
    # So, agent_service.run_agent and create_message *will* be called for lead-2.
    # Then, lead-2 is skipped for sending, and status is updated to 'failed'.

    # Let's adjust the mock_agent_service to return unique message IDs for clarity if needed,
    # or just ensure it's called twice. Current assertions cover this.

    # The issue might be in the mock_outreach_repository.create_message and get_message_by_id,
    # which currently always return the *same* mock_draft_message.
    # If agent_service.run_agent is called for lead-2, and it creates a *different* message,
    # then get_message_by_id will be called with a different ID (but mock returns same draft).

    # For this first pass, let's focus on verifying the overall flow and calls.
    # The lead_id in the agent_result should ideally match the lead being processed.
    # Let's refine mock_agent_service to return lead-specific message IDs.

    # --- Refined Mocking Strategy ---
    # mock_agent_service.run_agent.side_effect should return different results for different leads.
    mock_agent_service.run_agent.side_effect = [
        { # For lead-id-1
            "message_id": "mock-message-123-lead1",
            "subject": "Mock Subject for Lead 1",
            "message_content": "Email body for Lead 1.",
            "tier": "cold",
            "lead_id": "mock-lead-id-1"
        },
        { # For lead-id-2
            "message_id": "mock-message-456-lead2",
            "subject": "Mock Subject for Lead 2",
            "message_content": "Email body for Lead 2.",
            "tier": "cold",
            "lead_id": "mock-lead-id-2"
        }
    ]
    # Adjust mock_outreach_repository to return the correct draft based on ID
    def mock_get_message_by_id(msg_id):
        if msg_id == "mock-message-123-lead1":
            return OutreachMessage(id="mock-message-123-lead1", lead_id="mock-lead-id-1", status="draft", tier="cold", subject="Mock Subject for Lead 1", message_content="Email body for Lead 1.")
        elif msg_id == "mock-message-456-lead2":
            return OutreachMessage(id="mock-message-456-lead2", lead_id="mock-lead-id-2", status="draft", tier="cold", subject="Mock Subject for Lead 2", message_content="Email body for Lead 2.")
        return None
    mock_outreach_repository.get_message_by_id.side_effect = mock_get_message_by_id

    # Now, the calls to update_message_status should reflect two updates: one sent, one failed.
    # The 'sent_at' and 'failed_at' are set by the controller, so we check those.

    # Reset mocks for this specific test function if needed, or manage side_effects carefully.
    # The override_dependencies fixture runs before each test.
    # Let's re-assert after the side_effects are set up.

    # Re-running client.post and assertions after setting up side_effects
    response = client.post("/api/leads/send-bulk-emails?tier=cold")
    assert response.status_code == 202
    response_data = response.json()
    assert response_data["results"]["emails_sent"] == 1
    assert response_data["results"]["emails_failed"] == 1 # Lead 2 failed due to missing email
    assert response_data["results"]["emails_skipped_no_email"] == 1 # This count reflects the 'failed' count in this context

    mock_lead_repository.get_by_tier.assert_called_once_with("cold")
    assert mock_agent_service.run_agent.call_count == 2
    assert mock_outreach_repository.create_message.call_count == 2
    mock_outreach_repository.get_message_by_id.assert_any_call("mock-message-123-lead1")
    mock_outreach_repository.get_message_by_id.assert_any_call("mock-message-456-lead2")
    assert mock_outreach_repository.get_message_by_id.call_count == 2

    mock_email_service.send_email.assert_called_once_with( # Only called for lead-1
        to_email="test1@example.com",
        subject="Mock Subject for Lead 1",
        body="Email body for Lead 1.",
        lead_tier="cold",
        outreach_message=mock_outreach_repository.get_message_by_id("mock-message-123-lead1")
    )

    # Assert the two calls to update_message_status
    # Call 1: For lead-1 (sent)
    mock_outreach_repository.update_message_status.assert_any_call(
        msg_id="mock-message-123-lead1",
        status="sent",
        sent_at=pytest.approx(datetime.datetime.now(datetime.timezone.utc), abs=1)
    )
    # Call 2: For lead-2 (failed due to no email)
    mock_outreach_repository.update_message_status.assert_any_call(
        msg_id="mock-message-456-lead2",
        status="failed",
        failed_at=pytest.approx(datetime.datetime.now(datetime.timezone.utc), abs=1),
        failure_reason="Missing contact email"
    )
    assert mock_outreach_repository.update_message_status.call_count == 2


# Add tests for:
# - Invalid tier (400 Bad Request)
# - No leads found for a tier (200 OK, empty result)
# - AgentService failure
# - EmailService.send_email failure
# - Missing SMTP configuration (covered by EmailService dependency error)
