"""FastAPI webhook. Point your form (Tally, Typeform, Webflow, n8n, Zapier) at POST /webhook/lead."""
from __future__ import annotations

import logging

from fastapi import FastAPI, Header, HTTPException

from .config import settings
from .models import Lead, QualifiedLead
from .pipeline import LeadPipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="AI Lead Qualifier", version="1.0.0")
pipeline = LeadPipeline.from_settings(settings)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "provider": pipeline.qualifier.name, "telegram": pipeline.notifier.enabled}


@app.post("/webhook/lead", response_model=QualifiedLead)
def receive_lead(lead: Lead, x_webhook_secret: str | None = Header(default=None)) -> QualifiedLead:
    if settings.webhook_secret and x_webhook_secret != settings.webhook_secret:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")
    try:
        return pipeline.process(lead)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
