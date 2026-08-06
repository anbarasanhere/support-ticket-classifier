"""
FastAPI entry point for the AI-Powered Support Ticket Classifier.
"""
# Phase 1: Importing necessary libraries
import os
import logging 
from contextlib import asynccontextmanager # used to define startup/shutdown events

from dotenv import load_dotenv # loads environment variables from a .env file
from fastapi import FastAPI, HTTPException # core fastapi objects
from fastapi.middleware.cors import CORSMiddleware # allows browsers to access the API
from pydantic import BaseModel, Field # pydantic is responsible for data validation and parsing

from graph import run_pipeline 
from production_modules.prompt_versioning import list_versions, get_active_version
from production_modules.cost_calculator import session_tracker

# Phase 2: Configuring the application
load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s") 
logger = logging.getLogger(__name__) # creates a scoped logger using the current module name

# Phase 3: Defining the input 

class ClassifyRequest(BaseModel): # defines what the clients are allowed to send (request)
    ticket_text: str = Field(..., min_length=5, max_length=4000)
    channel: str = Field(default="web_form", pattern="^(web_form|email)$")

# Phase 4: Defining the output

class ClassifyResponse(BaseModel): # defines what the clients are allowed to receive (response)
    issue_category: str 
    assigned_team: str
    priority: str
    user_sentiment: str
    confidence_score: float
    reasoning: str
    requires_human_review: bool
    pii_detected: bool
    prompt_version: str | None
    cost_info: dict | None
    injection_blocked: bool


# ---------------------------------------------------------------------------
# Startup banner
# ---------------------------------------------------------------------------
def print_banner():
    model = os.getenv("DEFAULT_MODEL", "gpt-4o-mini")
    prompt_version = get_active_version()
    pii_enabled = True   # always on in this build
    cost_tracking = os.getenv("LOG_COSTS", "true").lower() == "true"

    banner = f"""
╔══════════════════════════════════════════════════════════╗
║       AI-Powered Support Ticket Classifier               ║
╠══════════════════════════════════════════════════════════╣
║  Model          : {model:<38} ║
║  Prompt Version : {prompt_version:<38} ║
║  PII Redaction  : {'enabled' if pii_enabled else 'disabled':<38} ║
║  Cost Tracking  : {'enabled' if cost_tracking else 'disabled':<38} ║
╚══════════════════════════════════════════════════════════╝
"""
    print(banner)


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    print_banner()
    yield
    summary = session_tracker.summary
    logger.info("Session ended. Total cost: $%.6f over %d calls", summary["total_cost_usd"], summary["calls"])


app = FastAPI(
    title="Support Ticket Classifier",
    description="LangGraph + FastAPI ticket classification pipeline",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/prompts")
async def get_prompts():
    return {"versions": list_versions(), "active": get_active_version()}


@app.post("/classify", response_model=ClassifyResponse)
async def classify(request: ClassifyRequest):
    try:
        state = run_pipeline(request.ticket_text, request.channel)
    except Exception as exc:
        logger.exception("Pipeline error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

    classification = state.get("classification")
    if classification is None:
        raise HTTPException(status_code=422, detail=state.get("error", "Classification failed"))

    return ClassifyResponse(
        issue_category=classification.issue_category.value,
        assigned_team=classification.assigned_team.value,
        priority=classification.priority.value,
        user_sentiment=classification.user_sentiment.value,
        confidence_score=classification.confidence_score,
        reasoning=classification.reasoning,
        requires_human_review=classification.requires_human_review,
        pii_detected=state.get("pii_detected", False),
        prompt_version=state.get("prompt_version"),
        cost_info=state.get("cost_info"),
        injection_blocked=state.get("injection_blocked", False),
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
