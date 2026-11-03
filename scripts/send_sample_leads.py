"""Send sample leads to a running server:  python scripts/send_sample_leads.py http://localhost:8000"""
import json
import sys
import urllib.request
from pathlib import Path

base = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
leads = json.loads((Path(__file__).parent / "sample_leads.json").read_text(encoding="utf-8"))

for lead in leads:
    req = urllib.request.Request(
        f"{base}/webhook/lead",
        data=json.dumps(lead).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        q = json.loads(resp.read())["qualification"]
        print(f"{q['priority']:<6} {q['score']:>3}  {lead['name']}: {q['summary']}")
