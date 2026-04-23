import asyncio
import uuid
import datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.future import select
from app.models.core import User, Opportunity, Briefing, Interaction
from app.core.security import get_password_hash
from app.api.dev import SEED_OPPORTUNITIES, DEFAULT_USER_ID
from app.database import Base

DATABASE_URL = "sqlite+aiosqlite:///./salesboost.db"
engine = create_async_engine(DATABASE_URL)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def seed():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    async with AsyncSessionLocal() as db:
        # Check if default user already exists
        result = await db.execute(select(User).where(User.email == "alex.stratos@salesboost.ai"))
        existing_user = result.scalar_one_or_none()
        
        if existing_user:
            print(f"User already exists, skipping seed.")
            return

        # Create default user
        user = User(
            id=DEFAULT_USER_ID,
            email="alex.stratos@salesboost.ai",
            hashed_password="$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGGa31S.", # 'password'
            role="executive",
        )
        db.add(user)
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
                    type="visit",
                    summary=f"Premier contact avec {data['company_name']} pour discuter de {data['title']}.",
                    raw_transcript="Assistant: Bonjour. Client: Bonjour, nous avons des problèmes de CRM...",
                    requirements={"description": data["title"], "platform": "Web"}
                )
                db.add(interaction)

        await db.commit()
        print(f"Seeded {len(SEED_OPPORTUNITIES)} opportunities and interactions.")

if __name__ == "__main__":
    asyncio.run(seed())
