"""Where qualified leads are stored. CSV works out of the box; Google Sheets is optional."""
from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Protocol

from .config import Settings
from .models import QualifiedLead

log = logging.getLogger(__name__)

COLUMNS = [
    "received_at", "priority", "score", "category", "budget_usd", "urgency",
    "name", "email", "company", "source", "summary", "message", "suggested_reply", "provider",
]


def to_row(item: QualifiedLead) -> list[str]:
    q, lead = item.qualification, item.lead
    values = {
        "received_at": item.received_at.isoformat(timespec="seconds"),
        "priority": q.priority.value,
        "score": q.score,
        "category": q.category.value,
        "budget_usd": q.budget_usd if q.budget_usd is not None else "",
        "urgency": q.urgency,
        "name": lead.name,
        "email": lead.email,
        "company": lead.company or "",
        "source": lead.source,
        "summary": q.summary,
        "message": lead.message,
        "suggested_reply": q.suggested_reply,
        "provider": item.provider,
    }
    return [str(values[c]) for c in COLUMNS]


class Sink(Protocol):
    def save(self, item: QualifiedLead) -> None: ...


class CsvSink:
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, item: QualifiedLead) -> None:
        new_file = not self.path.exists()
        with self.path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if new_file:
                writer.writerow(COLUMNS)
            writer.writerow(to_row(item))


class GoogleSheetsSink:  # pragma: no cover - requires Google credentials
    def __init__(self, sheet_id: str, credentials_file: str):
        import gspread

        client = gspread.service_account(filename=credentials_file)
        self.ws = client.open_by_key(sheet_id).sheet1
        if not self.ws.row_values(1):
            self.ws.append_row(COLUMNS)

    def save(self, item: QualifiedLead) -> None:
        self.ws.append_row(to_row(item), value_input_option="USER_ENTERED")


def build_sinks(settings: Settings) -> list[Sink]:
    sinks: list[Sink] = [CsvSink(settings.csv_path)]
    if settings.google_sheet_id and settings.google_credentials_file:
        try:
            sinks.append(GoogleSheetsSink(settings.google_sheet_id, settings.google_credentials_file))
        except Exception as exc:
            log.error("Google Sheets disabled: %s", exc)
    return sinks
