"""
Dev-only endpoints for seeding the database with realistic test data.
Not for production use.
"""
import uuid
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from ..database import get_db
from ..models.core import User, Opportunity, Briefing
from ..core.security import get_password_hash

router = APIRouter()

DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000001"

SEED_OPPORTUNITIES = [
    {
        "title": "Cloud Scale ERP Implementation",
        "company_name": "GlobalTech Industries",
        "stage": "discovery",
        "value": 240000.0,
        "win_probability": 0.15,
        "priority": "high",
        "ai_strategy": "Strategic focus for GlobalTech Industries: leverage their digital transformation mandate to position an AI-native ERP as the single source of truth across their 12 subsidiaries.",
        "ai_risk_assessment": "High dependency on legacy SAP connectors. Recommend early technical pre-sales involvement to de-risk integration complexity.",
        "market_insights": {
            "sector_trend": "Shift towards Real-time RAG in SalesTech.",
            "demand_index": "+22.4% MoM",
            "competitor_analysis": "Major competitors automating 70% of pre-sales qualification."
        }
    },
    {
        "title": "Fintech Payment Gateway Upgrade",
        "company_name": "FinCorp Solutions",
        "stage": "discovery",
        "value": 85000.0,
        "win_probability": 0.10,
        "priority": "medium",
        "ai_strategy": "FinCorp is in early evaluation. Focus on compliance automation and PCI-DSS certification acceleration as the primary value driver.",
        "ai_risk_assessment": "Budget cycle ends Q4. Procurement approval requires C-level sign-off — escalate early.",
        "market_insights": {
            "sector_trend": "Fintech compliance automation demand up 18% YoY.",
            "demand_index": "+18.2% MoM",
            "competitor_analysis": "Stripe and Adyen competing on price; differentiate on enterprise support."
        }
    },
    {
        "title": "HealthTech AI Patient Platform",
        "company_name": "MedCare Group",
        "stage": "proposal",
        "value": 110000.0,
        "win_probability": 0.45,
        "priority": "high",
        "ai_strategy": "MedCare is evaluating three vendors. Position the AI Copilot as a force-multiplier for their clinical staff, reducing documentation burden by 40%.",
        "ai_risk_assessment": "HIPAA compliance requirements add 6-week implementation overhead. Engage legal team early.",
        "market_insights": {
            "sector_trend": "AI in healthcare administration growing at 34% CAGR.",
            "demand_index": "+34.1% MoM",
            "competitor_analysis": "Epic Systems and Cerner competing on integrations; differentiate on AI-native approach."
        }
    },
    {
        "title": "Manufacturing ERP Consolidation",
        "company_name": "IndustrCo",
        "stage": "proposal",
        "value": 180000.0,
        "win_probability": 0.55,
        "priority": "medium",
        "ai_strategy": "IndustrCo is consolidating 4 legacy ERPs. Emphasize migration tooling and zero-downtime transition as key differentiators.",
        "ai_risk_assessment": "Union workforce regulations may delay go-live. Include change management in the proposal.",
        "market_insights": {
            "sector_trend": "Manufacturing ERP consolidation wave post-COVID.",
            "demand_index": "+12.8% MoM",
            "competitor_analysis": "SAP S/4HANA is the main competitor; highlight TCO advantage."
        }
    },
    {
        "title": "Retail Omnichannel Suite",
        "company_name": "RetailMax Group",
        "stage": "negotiation",
        "value": 420000.0,
        "win_probability": 0.80,
        "priority": "high",
        "ai_strategy": "RetailMax has completed technical validation. Focus negotiation on multi-year SLA terms and success-based pricing to accelerate signature.",
        "ai_risk_assessment": "Competitor submitted a revised proposal last week. Secure executive sponsorship to maintain momentum.",
        "market_insights": {
            "sector_trend": "Omnichannel retail tech consolidation accelerating.",
            "demand_index": "+28.6% MoM",
            "competitor_analysis": "Salesforce Commerce Cloud competing; price delta is 15% — justify with AI ROI data."
        }
    },
    {
        "title": "Insurance Data Analytics Platform",
        "company_name": "InsureLife",
        "stage": "negotiation",
        "value": 95000.0,
        "win_probability": 0.65,
        "priority": "medium",
        "ai_strategy": "InsureLife requires real-time actuarial modeling. Position the platform's streaming analytics as a 3x speed improvement over their current batch processing.",
        "ai_risk_assessment": "Regulatory approval from the insurance commission is required before contract signing. Timeline: 3-4 weeks.",
        "market_insights": {
            "sector_trend": "InsureTech data platforms growing at 21% CAGR.",
            "demand_index": "+21.3% MoM",
            "competitor_analysis": "Palantir competing on brand; differentiate on domain-specific templates."
        }
    },
    {
        "title": "Logistics Pro Automation Suite",
        "company_name": "LogiGroup International",
        "stage": "closed",
        "value": 32000.0,
        "win_probability": 1.0,
        "priority": "low",
        "ai_strategy": "Closed deal. Focus on successful onboarding and identifying upsell opportunities within their 8 regional offices.",
        "ai_risk_assessment": "Low risk. Post-sale: ensure CS team is engaged within 48 hours of contract signature.",
        "market_insights": {
            "sector_trend": "Last-mile delivery automation market expanding.",
            "demand_index": "+15.9% MoM",
            "competitor_analysis": "Deal won; no competitive threat at this stage."
        }
    },
]

SEED_CAMPAIGNS = [
    {
        "name": "Campagne Q2 2026 - Expansion Logistique",
        "description": "Focus sur les entreprises de logistique du Grand Ouest.",
        "status": "active"
    },
    {
        "name": "Opération Fintech 2026",
        "description": "Ciblage des startups Fintech en levée de fonds Serie A.",
        "status": "active"
    }
]


@router.post("/seed", summary="Seed database with realistic test data", tags=["Dev"])
async def seed_database(db: AsyncSession = Depends(get_db)):
    """
    Idempotent seed endpoint: creates a default user and sample opportunities
    if they don't already exist.
    """
    from ..models.core import Campaign, Interaction
    import datetime

    # Check if default user already exists
    result = await db.execute(select(User).where(User.id == DEFAULT_USER_ID))
    existing_user = result.scalar_one_or_none()

    if existing_user:
        return {"status": "already_seeded", "user_id": str(DEFAULT_USER_ID)}

    # Create default user
    user = User(
        id=DEFAULT_USER_ID,
        email="alex.stratos@salesboost.ai",
        hashed_password=get_password_hash("demo1234"),
        role="executive",
    )
    db.add(user)
    await db.flush()

    # Create Campaigns
    campaigns = []
    for c_data in SEED_CAMPAIGNS:
        campaign = Campaign(
            name=c_data["name"],
            description=c_data["description"],
            status=c_data["status"],
            start_date=datetime.datetime.now(datetime.timezone.utc),
            end_date=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=90)
        )
        db.add(campaign)
        campaigns.append(campaign)
    await db.flush()

    # Create opportunities + briefings
    for i, data in enumerate(SEED_OPPORTUNITIES):
        opp = Opportunity(
            title=data["title"],
            company_name=data["company_name"],
            stage=data["stage"],
            value=data["value"],
            win_probability=data["win_probability"],
            priority=data["priority"],
            owner_id=DEFAULT_USER_ID,
        )
        db.add(opp)
        await db.flush()

        briefing = Briefing(
            opportunity_id=opp.id,
            ai_strategy=data["ai_strategy"],
            ai_risk_assessment=data["ai_risk_assessment"],
            market_insights=data["market_insights"],
        )
        db.add(briefing)

        # Add a sample interaction for some opportunities
        if i % 2 == 0:
            interaction = Interaction(
                opportunity_id=opp.id,
                campaign_id=campaigns[0].id if i < 4 else campaigns[1].id,
                type="visit",
                summary=f"Premier contact avec {data['company_name']} pour discuter de {data['title']}.",
                raw_transcript="Assistant: Bonjour. Client: Bonjour, nous avons des problèmes de CRM...",
                requirements={"description": data["title"], "platform": "Web"}
            )
            db.add(interaction)

    await db.commit()

    return {
        "status": "seeded",
        "user_id": str(DEFAULT_USER_ID),
        "opportunities": len(SEED_OPPORTUNITIES),
        "campaigns": len(SEED_CAMPAIGNS)
    }
