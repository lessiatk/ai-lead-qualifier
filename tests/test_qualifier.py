import json

import pytest

from app.models import Category, Lead, Priority
from app.notifier import format_alert
from app.pipeline import LeadPipeline
from app.qualifier import MockQualifier, _extract_json, parse_budget
from app.sinks import COLUMNS, CsvSink


@pytest.mark.parametrize(
    ("text", "expected"),
    [("$5k", 5000), ("2-3k", 3000), ("1,500 USD", 1500), ("€800", 800), (None, None), ("tbd", None)],
)
def test_parse_budget(text, expected):
    assert parse_budget(text) == expected


def test_extract_json_handles_code_fences():
    raw = 'Sure! ```json\n{"score": 80, "priority": "hot"}\n```'
    assert _extract_json(raw) == {"score": 80, "priority": "hot"}


def test_good_lead_is_hot():
    lead = Lead(
        name="Mark Jensen",
        email="mark@example.com",
        company="Nordic Parts",
        message="Need an n8n automation that updates our Google Sheet from supplier emails. Start ASAP.",
        budget="$3k",
    )
    q = MockQualifier().qualify(lead)
    assert q.category == Category.automation
    assert q.budget_usd == 3000
    assert q.priority == Priority.hot
    assert "Mark" in q.suggested_reply


def test_off_topic_lead_is_cold():
    lead = Lead(name="Tom", email="tom@example.com", message="Can you design a logo for my bakery?")
    q = MockQualifier().qualify(lead)
    assert q.category == Category.other
    assert q.priority == Priority.cold


class FakeNotifier:
    enabled = True

    def __init__(self):
        self.sent: list[str] = []

    def send(self, text: str) -> None:
        self.sent.append(text)


def test_pipeline_saves_csv_and_alerts_only_hot(tmp_path):
    csv_path = tmp_path / "leads.csv"
    notifier = FakeNotifier()
    pipeline = LeadPipeline(MockQualifier(), [CsvSink(str(csv_path))], notifier)

    with open("scripts/sample_leads.json", encoding="utf-8") as f:
        leads = [Lead.model_validate(x) for x in json.load(f)]
    results = [pipeline.process(lead) for lead in leads]

    rows = csv_path.read_text(encoding="utf-8").splitlines()
    assert rows[0].split(",")[: len(COLUMNS)] == COLUMNS
    assert len(rows) == len(leads) + 1
    hot = [r for r in results if r.qualification.priority == Priority.hot]
    assert hot and len(notifier.sent) == len(hot)


def test_alert_escapes_html():
    lead = Lead(name="<script>", email="x@example.com", message="scraper for prices", budget="$2k")
    item = LeadPipeline(MockQualifier(), [], FakeNotifier()).process(lead)
    assert "<script>" not in format_alert(item)


def test_api_webhook(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    monkeypatch.setenv("LEADS_CSV_PATH", str(tmp_path / "leads.csv"))
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    assert client.get("/health").json()["status"] == "ok"
    resp = client.post("/webhook/lead", json={"name": "A", "email": "a@b.co", "message": "need a gpt chatbot"})
    assert resp.status_code == 200
    assert resp.json()["qualification"]["category"] == "ai_integration"
