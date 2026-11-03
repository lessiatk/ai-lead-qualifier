"""Telegram alerts for hot leads. Without a bot token it just logs the message."""
from __future__ import annotations

import html
import json
import logging
import urllib.request

from .config import Settings
from .models import QualifiedLead

log = logging.getLogger(__name__)

EMOJI = {"hot": "🔥", "warm": "🌤", "cold": "❄️"}


def format_alert(item: QualifiedLead) -> str:
    q, lead = item.qualification, item.lead
    e = html.escape
    budget = f"${q.budget_usd:,}" if q.budget_usd else "not stated"
    return (
        f"{EMOJI[q.priority.value]} <b>{q.priority.value.upper()} lead</b> — score {q.score}/100\n"
        f"<b>{e(lead.name)}</b>{' · ' + e(lead.company) if lead.company else ''}\n"
        f"📧 {e(lead.email)}\n"
        f"🏷 {q.category.value.replace('_', ' ')} · 💰 {budget} · ⏱ urgency {q.urgency}/5\n\n"
        f"{e(q.summary)}\n\n"
        f"<i>Suggested reply:</i>\n{e(q.suggested_reply)}"
    )


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str):
        self.token, self.chat_id = token, chat_id

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    def send(self, text: str) -> None:
        if not self.enabled:
            log.info("[telegram disabled] would send:\n%s", text)
            return
        payload = json.dumps({"chat_id": self.chat_id, "text": text, "parse_mode": "HTML"}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{self.token}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310 - fixed https URL
                resp.read()
        except Exception as exc:  # never let a failed alert lose the lead
            log.error("Telegram send failed: %s", exc)


def build_notifier(settings: Settings) -> TelegramNotifier:
    return TelegramNotifier(settings.telegram_bot_token, settings.telegram_chat_id)
