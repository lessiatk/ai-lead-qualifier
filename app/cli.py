"""Run the pipeline on a JSON file of leads without starting a server:  python -m app.cli scripts/sample_leads.json"""
from __future__ import annotations

import argparse
import json
import logging

from .config import settings
from .models import Lead
from .pipeline import LeadPipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Qualify leads from a JSON file")
    parser.add_argument("file", help="JSON file with a list of leads")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    pipeline = LeadPipeline.from_settings(settings)

    with open(args.file, encoding="utf-8") as f:
        leads = [Lead.model_validate(x) for x in json.load(f)]

    print(f"\nProvider: {pipeline.qualifier.name}\n")
    print(f"{'PRIORITY':<9}{'SCORE':>5}  {'CATEGORY':<15}{'BUDGET':>9}  LEAD")
    for lead in leads:
        q = pipeline.process(lead).qualification
        budget = f"${q.budget_usd:,}" if q.budget_usd else "—"
        print(f"{q.priority.value:<9}{q.score:>5}  {q.category.value:<15}{budget:>9}  {lead.name} ({lead.company or '-'})")
    print(f"\nSaved to {settings.csv_path}")


if __name__ == "__main__":
    main()
