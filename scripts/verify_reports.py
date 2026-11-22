"""Verify every request ID / timestamp cited in the final reports against evidence, and recompute key metrics."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"


def evidence_index() -> dict[str, list[dict]]:
    idx: dict[str, list[dict]] = {}
    for f in sorted((ROOT / "evidence" / "runs").glob("*/results.json")):
        run = json.loads(f.read_text(encoding="utf-8"))
        for c in run["cases"]:
            for r in c["requests"]:
                ids = set(re.findall(UUID, json.dumps(r["request_ids"]))) | set(re.findall(UUID, r.get("body_excerpt") or ""))
                for i in ids:
                    idx.setdefault(i, []).append({"run": run["run_id"], "case": c["case_id"], "seq": r["ledger_seq"],
                                                  "utc": r["timestamp_utc"], "status": r["status"]})
    return idx


def check_report(path: Path, idx: dict) -> list[str]:
    s = path.read_text(encoding="utf-8")
    problems = []
    for m in re.finditer(rf"`({UUID})`(?:[^`\n]{{0,40}}?\(?(\d{{2}}:\d{{2}}(?::\d{{2}})?)\)?)?", s):
        rid, t = m.group(1), m.group(2)
        hits = idx.get(rid)
        if not hits:
            problems.append(f"{path.name}: {rid} not found in evidence")
            continue
        if t and not any(h["utc"][11:11 + len(t)] == t for h in hits):
            problems.append(f"{path.name}: {rid} cited at {t}, evidence {[h['utc'][11:19] for h in hits]}")
    return problems


def recompute() -> dict:
    runs = [json.loads(f.read_text(encoding="utf-8")) for f in sorted((ROOT / "evidence" / "runs").glob("*/results.json"))]
    led = [json.loads(line) for line in (ROOT / "evidence" / "request-ledger.jsonl").read_text().splitlines() if line]
    f1 = sync = 0
    for run in runs:
        for c in run["cases"]:
            for r in c["requests"]:
                ex = r.get("body_excerpt") or ""
                if r["endpoint"] in ("/waves/v1/tts", "/waves/v1/tts/live") and r["status"] == 400 and ex.startswith('{"error":['):
                    f1 += 1
                if r["endpoint"] == "/waves/v1/tts" and r["status"] == 200 and r["request"].get("text_chars"):
                    sync += 1
    return {"ledger_total": len(led), "phase1": sum(1 for e in led if e.get("phase", 1) == 1),
            "phase2": sum(1 for e in led if e.get("phase") == 2), "f1_array_error_responses": f1,
            "sync_tts_200_samples": sync,
            "first_utc": led[0]["utc"], "last_utc": led[-1]["utc"]}


def main() -> int:
    idx = evidence_index()
    problems = []
    for name in ("final-submission.md", "final-engineering-report.md"):
        problems += check_report(ROOT / "reports" / name, idx)
    sub = (ROOT / "reports" / "final-submission.md").read_text(encoding="utf-8")
    words = len(re.findall(r"\S+", sub))
    facts = recompute()
    print(json.dumps({"submission_words": words, **facts}, indent=1))
    if words >= 1500:
        problems.append(f"submission has {words} words (limit 1500)")
    for p in problems:
        print("PROBLEM:", p)
    print("verified" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
