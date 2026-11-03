"""Lead qualification: one interface, three providers (mock, OpenAI, Anthropic)."""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Protocol

from pydantic import ValidationError

from .config import Settings
from .models import Category, Lead, Priority, Qualification

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You qualify inbound sales leads for a freelance Python & AI automation engineer.
Services offered: workflow automation (n8n + Python), AI/LLM integrations, web scraping & data pipelines, backend APIs.

Return ONLY a JSON object with these fields:
- category: one of automation | ai_integration | web_scraping | backend_api | other
- budget_usd: integer best estimate in USD, or null if unknown
- urgency: integer 1-5 (5 = needs it this week)
- score: integer 0-100, how likely this is a good-fit, paying project
- priority: hot | warm | cold
- summary: one sentence for the sales team
- suggested_reply: a short, friendly first reply to the lead (2-4 sentences)

Scoring guide: clear scope + budget >= $1000 + fits services = 70+. Vague, no budget, or off-topic = below 40."""


class Qualifier(Protocol):
    name: str

    def qualify(self, lead: Lead) -> Qualification: ...


def _lead_to_prompt(lead: Lead) -> str:
    return json.dumps(lead.model_dump(), ensure_ascii=False, indent=2)


def _extract_json(text: str) -> dict:
    """LLMs sometimes wrap JSON in ```json fences or add a sentence around it."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object in model output: {text[:200]!r}")
    return json.loads(match.group(0))


def parse_budget(text: str | None) -> int | None:
    """'$5k' -> 5000, '2-3k' -> 3000, '1,500 USD' -> 1500, '€800' -> 800."""
    if not text:
        return None
    t = text.lower().replace(",", "").replace(" ", "")
    matches = re.findall(r"(\d+(?:\.\d+)?)(k?)", t)
    if not matches:
        return None
    # "2-3k": the trailing k applies to the whole range
    range_k = t.rstrip("usd$€").endswith("k")
    values = [float(n) * (1000 if (k or range_k) else 1) for n, k in matches]
    return int(max(values))


class MockQualifier:
    """Deterministic keyword heuristics. Lets anyone run the demo without API keys."""

    name = "mock"

    _KEYWORDS: dict[Category, tuple[str, ...]] = {
        Category.web_scraping: ("scrap", "parse", "crawl", "extract data", "competitor", "prices"),
        Category.ai_integration: ("gpt", "openai", "llm", "chatbot", "claude", "rag", " ai ", "ai-"),
        Category.automation: ("automat", "n8n", "zapier", "make.com", "workflow", "sheets", "crm"),
        Category.backend_api: ("api", "backend", "fastapi", "django", "database"),
    }
    _URGENT = ("asap", "urgent", "this week", "tomorrow", "deadline", "immediately")

    def qualify(self, lead: Lead) -> Qualification:
        text = f" {lead.message} {lead.company or ''} ".lower()

        hits = {cat: sum(kw in text for kw in kws) for cat, kws in self._KEYWORDS.items()}
        best_cat, best_hits = max(hits.items(), key=lambda kv: kv[1])
        category = best_cat if best_hits else Category.other

        budget = parse_budget(lead.budget) or parse_budget(
            m.group(0) if (m := re.search(r"\$\s?\d[\d,]*k?", lead.message)) else None
        )
        urgency = 5 if any(w in text for w in self._URGENT) else 3 if "soon" in text else 2

        score = 15
        score += 25 if category != Category.other else 0
        score += 15 if lead.company else 0
        score += 10 if len(lead.message) > 120 else -10 if len(lead.message) < 40 else 0
        if budget:
            score += 30 if budget >= 1000 else 15 if budget >= 300 else -10
        score += 5 * (urgency - 2) if urgency > 2 else 0
        score = max(0, min(100, score))

        priority = Priority.hot if score >= 70 else Priority.warm if score >= 40 else Priority.cold
        first_name = lead.name.split()[0]
        label = category.value.replace("_", " ")

        return Qualification(
            category=category,
            budget_usd=budget,
            urgency=urgency,
            score=score,
            priority=priority,
            summary=f"{label.capitalize()} request from {lead.company or lead.name}"
            + (f", budget ~${budget:,}" if budget else ", budget not stated"),
            suggested_reply=(
                f"Hi {first_name}, thanks for reaching out! Your {label} task sounds like a great fit. "
                "Could you share a bit more about the current process and the timeline? "
                "I'll come back with a short plan and an estimate."
            ),
        )


class _LLMQualifier:
    """Shared retry + validation loop for real providers."""

    name = "llm"
    max_attempts = 3

    def _complete(self, user_prompt: str) -> str:  # pragma: no cover - network
        raise NotImplementedError

    def qualify(self, lead: Lead) -> Qualification:
        prompt = _lead_to_prompt(lead)
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                raw = self._complete(prompt)
                return Qualification.model_validate(_extract_json(raw))
            except (ValidationError, ValueError, json.JSONDecodeError) as exc:
                last_error = exc
                log.warning("Invalid model output (attempt %s/%s): %s", attempt, self.max_attempts, exc)
                prompt = f"{_lead_to_prompt(lead)}\n\nYour previous answer was invalid: {exc}. Return valid JSON only."
            except Exception as exc:  # network / rate limit
                last_error = exc
                log.warning("Provider error (attempt %s/%s): %s", attempt, self.max_attempts, exc)
                time.sleep(2**attempt)
        raise RuntimeError(f"Qualification failed after {self.max_attempts} attempts") from last_error


class OpenAIQualifier(_LLMQualifier):
    name = "openai"

    def __init__(self, api_key: str, model: str):
        from openai import OpenAI  # imported lazily so mock mode needs no SDK

        self._client = OpenAI(api_key=api_key)
        self._model = model

    def _complete(self, user_prompt: str) -> str:  # pragma: no cover - network
        resp = self._client.chat.completions.create(
            model=self._model,
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}],
        )
        return resp.choices[0].message.content or ""


class AnthropicQualifier(_LLMQualifier):
    name = "anthropic"

    def __init__(self, api_key: str, model: str):
        from anthropic import Anthropic

        self._client = Anthropic(api_key=api_key)
        self._model = model

    def _complete(self, user_prompt: str) -> str:  # pragma: no cover - network
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=800,
            temperature=0.2,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return "".join(block.text for block in resp.content if block.type == "text")


def build_qualifier(settings: Settings) -> Qualifier:
    provider = settings.llm_provider.lower()
    if provider == "openai" and settings.openai_api_key:
        return OpenAIQualifier(settings.openai_api_key, settings.openai_model)
    if provider == "anthropic" and settings.anthropic_api_key:
        return AnthropicQualifier(settings.anthropic_api_key, settings.anthropic_model)
    if provider != "mock":
        log.warning("LLM_PROVIDER=%s but no API key set — falling back to mock mode", provider)
    return MockQualifier()
