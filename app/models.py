from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class Lead(BaseModel):
    """Raw lead as it arrives from a website form, Typeform, Tally, etc."""

    name: str = Field(..., min_length=1, max_length=200)
    email: str = Field(..., max_length=320)
    company: str | None = Field(default=None, max_length=200)
    message: str = Field(..., min_length=1, max_length=5000)
    budget: str | None = Field(default=None, max_length=100, description="Free text, e.g. '$5k' or '2-3k'")
    source: str = Field(default="website", max_length=50)


class Category(str, Enum):
    automation = "automation"
    ai_integration = "ai_integration"
    web_scraping = "web_scraping"
    backend_api = "backend_api"
    other = "other"


class Priority(str, Enum):
    hot = "hot"
    warm = "warm"
    cold = "cold"


class Qualification(BaseModel):
    """Structured output the LLM must return."""

    category: Category
    budget_usd: int | None = Field(default=None, ge=0, description="Best estimate of budget in USD")
    urgency: int = Field(..., ge=1, le=5, description="1 = no rush, 5 = needs it this week")
    score: int = Field(..., ge=0, le=100)
    priority: Priority
    summary: str = Field(..., max_length=300, description="One-sentence summary for the sales team")
    suggested_reply: str = Field(..., max_length=1000)


class QualifiedLead(BaseModel):
    lead: Lead
    qualification: Qualification
    received_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    provider: str
