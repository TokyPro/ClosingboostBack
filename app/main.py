import asyncio
import sys

# Set ProactorEventLoopPolicy on Windows for Playwright/Crawl4AI support
# This must be done before any other imports that might initialize an event loop.
if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception:
        pass

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from .api import opportunities
from .api import copilot
from .api import dev
from .api import users
from .api import documents
from .api import interactions
from .api import admin as admin_api
from .api import leads
from .api import scoring as scoring_api
from .api import agents as agents_api
from .core.config import settings
from .database import create_db_and_tables

@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_db_and_tables()
    yield

app = FastAPI(
    title="SalesBoost AI - Intelligence Console API",
    description="""
    Core API for SalesBoost AI, empowering sales teams with 'Digital Executive' insights.

    ### Features
    - **N-Tier Architecture**: Clean separation of API, Services, and Repositories.
    - **AI RAG Orchestration**: Powered by **Gemini 2.5 Pro** and **Google File Search**.
    - **Sales Pipeline**: Real-time tracking and strategic briefings.

    ### Quick start (dev)
    POST `/api/dev/seed` to populate the database with realistic test data.
    """,
    version="1.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://35.205.217.120",
        "http://35.205.217.120:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = exc.errors()
    if errors:
        first = errors[0]
        field = " → ".join(str(loc) for loc in first["loc"] if loc not in ("body", "query"))
        msg = first.get("msg", "Invalid value")
        detail = f"Field '{field}': {msg}" if field else msg
    else:
        detail = "Invalid request data"
    return JSONResponse(status_code=422, content={"detail": detail})

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected error occurred. Please try again."},
    )

app.include_router(opportunities.router, prefix="/api/opportunities", tags=["Sales Pipeline"])
app.include_router(interactions.router, prefix="/api/interactions", tags=["Interactions"])
app.include_router(copilot.router, prefix="/api/copilot", tags=["Copilot"])
app.include_router(users.router, prefix="/api/users", tags=["Users"])
app.include_router(dev.router, prefix="/api/dev", tags=["Dev"])
app.include_router(documents.router, prefix="/api/documents", tags=["Knowledge Base"])
app.include_router(admin_api.router, prefix="/api/admin", tags=["Admin"])
app.include_router(leads.router, prefix="/api/leads", tags=["Lead Intelligence"])
app.include_router(scoring_api.router, prefix="/api/scoring", tags=["Scoring & Segmentation"])
app.include_router(agents_api.router, prefix="/api/agents", tags=["AI Agents"])

@app.get("/", tags=["System"])
async def health_check():
    return {"status": "online", "engine": settings.GEMINI_MODEL, "rag": "Google File Search"}
