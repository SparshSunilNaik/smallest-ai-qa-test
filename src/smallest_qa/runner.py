"""Executes selected cases sequentially and writes sanitized evidence."""

from __future__ import annotations

import json
import platform
import sys
from pathlib import Path

import httpx

from . import __version__
from .budget import BudgetExceeded, RequestLedger
from .cases import CASES, CaseSpec, Context
from .client import HaltRun, QAClient
from .config import Settings
from .fixtures import ensure_stt_fixture
from .results import INCONCLUSIVE, NOT_TESTED, CaseResult, auto_classify
from .timeutil import run_id as make_run_id
from .timeutil import stamp_pair


class SecretLeak(RuntimeError):
    pass


def select_cases(only: list[str] | None, include_optional: bool) -> list[CaseSpec]:
    if only:
        wanted = {c.upper() for c in only}
        unknown = wanted - {c.case_id for c in CASES}
        if unknown:
            raise SystemExit(f"Unknown case id(s): {', '.join(sorted(unknown))}")
        return [c for c in CASES if c.case_id in wanted]
    return [c for c in CASES if include_optional or not c.optional]


def ledger_for(settings: Settings) -> RequestLedger:
    return RequestLedger(settings.evidence_dir / "request-ledger.jsonl", settings.max_requests)


def assert_no_secret(serialized: str, settings: Settings) -> None:
    if settings.api_key and settings.api_key in serialized:
        raise SecretLeak("API key found in evidence payload; refusing to write")


def execute(settings: Settings, specs: list[CaseSpec], *, transport: httpx.BaseTransport | None = None,
            sleep=None, log=print, fixture_provider=ensure_stt_fixture) -> Path:
    base_rid = rid = make_run_id()
    n = 1
    while (settings.evidence_dir / "runs" / rid).exists():  # never overwrite an earlier run's evidence
        n += 1
        rid = f"{base_rid}-{n}"
    ledger = ledger_for(settings)
    run_dir = settings.evidence_dir / "runs" / rid
    run_dir.mkdir(parents=True)
    private_dir = settings.evidence_dir / "private" / rid
    needs_fixture = any(s.case_id.startswith("STT") for s in specs)
    fixture = fixture_provider() if needs_fixture else None

    kwargs = {"transport": transport}
    if sleep is not None:
        kwargs["sleep"] = sleep
    results: list[CaseResult] = []
    halted: str | None = None
    started = stamp_pair()
    with QAClient(settings, ledger, rid, **kwargs) as client:
        ctx = Context(client=client, run_id=rid, private_dir=private_dir, fixture=fixture)
        for spec in specs:
            res = CaseResult(spec.case_id, spec.title, spec.area, spec.expected, list(spec.doc_refs))
            results.append(res)
            if halted:
                res.notes.append(f"Not executed: run halted ({halted})")
                continue
            if ledger.remaining < spec.planned_requests:
                res.notes.append(f"Not executed: needs {spec.planned_requests} request(s), "
                                 f"{ledger.remaining} left in cumulative budget")
                continue
            try:
                spec.run(ctx, res)
                if res.classification == NOT_TESTED and res.exchanges:
                    res.classification = auto_classify(res)
            except BudgetExceeded as exc:
                res.notes.append(str(exc))
                res.classification = auto_classify(res) if res.exchanges else NOT_TESTED
                halted = "cumulative request budget exhausted"
            except HaltRun as exc:
                halted = str(exc)
                res.notes.append(f"Halted: {exc}")
                res.classification = INCONCLUSIVE if res.exchanges else NOT_TESTED
            if client.guard.halt_reason and not halted:
                halted = client.guard.halt_reason
                res.notes.append(f"Safety stop triggered after this case: {halted}")
            log(f"  {spec.case_id:<8} {res.classification:<42} requests={len(res.exchanges)}")

    secrets = client.secrets
    payload = {
        "run_id": rid,
        "started": started,
        "finished": stamp_pair(),
        "harness_version": __version__,
        "environment": {"python": sys.version.split()[0], "httpx": httpx.__version__,
                        "platform": platform.platform(), "base_url": settings.base_url},
        "api_key_configured": settings.key_configured,
        "halted": halted,
        "requests_this_run": sum(len(r.exchanges) for r in results),
        "ledger_used_after_run": ledger.used,
        "ledger_cap": ledger.max_requests,
        "fixture": fixture.describe() if fixture else None,
        "cases": [r.to_dict(secrets) for r in results],
    }
    serialized = json.dumps(payload, indent=2, ensure_ascii=False, default=str)
    assert_no_secret(serialized, settings)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "results.json").write_text(serialized + "\n", encoding="utf-8")
    summary = render_run_summary(payload)
    assert_no_secret(summary, settings)
    (run_dir / "summary.md").write_text(summary, encoding="utf-8")
    return run_dir


def render_run_summary(payload: dict) -> str:
    lines = [
        f"# Run {payload['run_id']}",
        "",
        f"- Started: {payload['started']['utc']} (UTC) / {payload['started']['ist']} (IST)",
        f"- Requests this run: {payload['requests_this_run']}; cumulative ledger: "
        f"{payload['ledger_used_after_run']}/{payload['ledger_cap']}",
        f"- Halted: {payload['halted'] or 'no'}",
        "",
        "| Case | Classification | Status codes | Duration ms | TTFB ms | Failed checks |",
        "|---|---|---|---|---|---|",
    ]
    for c in payload["cases"]:
        statuses = ", ".join(str(r["status"]) for r in c["requests"]) or "-"
        durs = ", ".join(str(r["duration_ms"]) for r in c["requests"]) or "-"
        ttfb = ", ".join(str(r["ttfb_ms"]) for r in c["requests"]) or "-"
        failed = "; ".join(f"{k['name']} (expected {k['expected']}, got {k['actual']})"
                           for k in c["checks"] if k["passed"] is False) or "-"
        if len(c["requests"]) > 3:
            durs, ttfb = f"see results.json ({len(c['requests'])} samples)", "-"
        lines.append(f"| {c['case_id']} | {c['classification']} | {statuses} | {durs} | {ttfb} | "
                     f"{failed.replace('|', '/')} |")
    lines.append("")
    return "\n".join(lines)
