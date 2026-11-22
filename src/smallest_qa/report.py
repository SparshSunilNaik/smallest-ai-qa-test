"""Cross-run aggregation. A candidate is promoted to "Confirmed defect" only when the same
documented checks fail in at least two separate runs (reproduction)."""

from __future__ import annotations

import json
from pathlib import Path

from .results import CANDIDATE, CLASSIFICATIONS, CONFIRMED_DEFECT, DOCUMENTED


def load_runs(evidence_dir: Path) -> list[dict]:
    runs = []
    for path in sorted((evidence_dir / "runs").glob("*/results.json")):
        runs.append(json.loads(path.read_text(encoding="utf-8")))
    return runs


def _doc_failures(case: dict) -> frozenset[str]:
    return frozenset(c["name"] for c in case["checks"] if c["passed"] is False and c["requirement"] == DOCUMENTED)


def aggregate(runs: list[dict]) -> dict[str, dict]:
    """Return per-case aggregate keyed by case id, with final classification."""
    out: dict[str, dict] = {}
    for run in runs:
        for case in run["cases"]:
            agg = out.setdefault(case["case_id"], {"title": case["title"], "observations": []})
            agg["observations"].append({"run_id": run["run_id"], "classification": case["classification"],
                                        "doc_failures": _doc_failures(case), "case": case})
    for agg in out.values():
        executed = [o for o in agg["observations"] if o["case"]["requests"]]
        latest = executed[-1] if executed else agg["observations"][-1]
        final = latest["classification"]
        if final == CANDIDATE and latest["doc_failures"]:
            same = [o for o in executed if o["classification"] == CANDIDATE
                    and o["doc_failures"] == latest["doc_failures"]]
            if len({o["run_id"] for o in same}) >= 2:
                final = CONFIRMED_DEFECT
            agg["reproductions"] = len(same)
        agg["final"] = final
        agg["latest"] = latest
        agg["runs_executed"] = len(executed)
    return out


def render(evidence_dir: Path, ledger_used: int, ledger_cap: int) -> str:
    runs = load_runs(evidence_dir)
    agg = aggregate(runs)
    counts = {c: 0 for c in CLASSIFICATIONS}
    for a in agg.values():
        counts[a["final"]] += 1
    lines = ["# Results summary (auto-generated from evidence/runs)", "",
             f"- Runs: {len(runs)}; cumulative API requests (ledger): {ledger_used}/{ledger_cap}", "",
             "## Classification counts", ""]
    lines += [f"- {k}: {v}" for k, v in counts.items()]
    lines += ["", "## Per case (latest executed observation)", "",
              "| Case | Title | Final classification | Runs | Latest run | Status codes |", "|---|---|---|---|---|---|"]
    for cid, a in sorted(agg.items()):
        statuses = ", ".join(str(r["status"]) for r in a["latest"]["case"]["requests"]) or "-"
        lines.append(f"| {cid} | {a['title']} | {a['final']} | {a['runs_executed']} | {a['latest']['run_id']} | "
                     f"{statuses} |")
    lines.append("")
    return "\n".join(lines)
