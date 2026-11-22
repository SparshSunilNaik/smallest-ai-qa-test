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
from .budget import estimate_usd
from .config import MAX_BATCH_REQUESTS, PHASE_REQUEST_CAPS, PHASE_USD_CAPS, Settings
from .fixtures import ensure_stt_fixture
from .redact import scrub_paths
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
    return RequestLedger(settings.evidence_dir / "request-ledger.jsonl", settings.max_requests,
                         phase_caps=PHASE_REQUEST_CAPS, phase_usd_caps=PHASE_USD_CAPS)


def assert_no_secret(serialized: str, settings: Settings) -> None:
    if settings.api_key and settings.api_key in serialized:
        raise SecretLeak("API key found in evidence payload; refusing to write")


def _planned(spec: CaseSpec) -> int:
    return spec.max_requests or spec.planned_requests


def check_batch(settings: Settings, specs: list[CaseSpec], phase: int) -> list[str]:
    """Pre-flight refusals for a Phase 2+ batch (empty list = OK)."""
    problems = []
    ledger = ledger_for(settings)
    need = sum(_planned(s) for s in specs)
    if phase >= 2 and need > MAX_BATCH_REQUESTS:
        problems.append(f"batch plans {need} requests; maximum per batch is {MAX_BATCH_REQUESTS}")
    if need > ledger.phase_remaining(phase):
        problems.append(f"batch plans {need} requests; phase {phase} has {ledger.phase_remaining(phase)} left")
    usd_cap = PHASE_USD_CAPS.get(phase)
    if usd_cap is not None:
        projected = ledger.phase_est_usd(phase) + sum(
            estimate_usd(s.synth_chars, s.stt_audio_seconds + s.stt_audio_requests * 6.0) for s in specs)
        if projected > usd_cap:
            problems.append(f"projected phase {phase} spend ${projected:.2f} exceeds cap ${usd_cap:.2f}")
    return problems


def execute(settings: Settings, specs: list[CaseSpec], *, transport: httpx.BaseTransport | None = None,
            sleep=None, log=print, fixture_provider=ensure_stt_fixture, phase: int = 1, batch: str = "",
            p2_fixture_provider=None, doc_example_mode: str = "live") -> Path:
    if phase >= 2:
        problems = check_batch(settings, specs, phase)
        if problems:
            raise SystemExit("Refusing batch: " + "; ".join(problems))
    base_rid = rid = make_run_id()
    n = 1
    while (settings.evidence_dir / "runs" / rid).exists():  # never overwrite an earlier run's evidence
        n += 1
        rid = f"{base_rid}-{n}"
    ledger = ledger_for(settings)
    run_dir = settings.evidence_dir / "runs" / rid
    run_dir.mkdir(parents=True)
    private_dir = settings.evidence_dir / "private" / rid
    needs_fixture = any(s.case_id.startswith("STT") or s.phase >= 2 for s in specs)
    fixture = fixture_provider() if needs_fixture else None
    p2_ids = sorted({f for s in specs for f in s.p2_fixtures})
    p2_fixtures: dict = {}
    if p2_ids:
        from .fixtures_p2 import RECIPES_BY_ID, build

        def default_p2(ids):
            out = {}
            for fid in ids:
                try:
                    out[fid] = build(RECIPES_BY_ID[fid])
                except (FileNotFoundError, RuntimeError) as exc:
                    out[fid] = f"unavailable: {exc}"
            return out

        p2_fixtures = (p2_fixture_provider or default_p2)(p2_ids)

    kwargs = {"transport": transport, "phase": phase, "batch": batch}
    if sleep is not None:
        kwargs["sleep"] = sleep
    results: list[CaseResult] = []
    halted: str | None = None
    started = stamp_pair()
    with QAClient(settings, ledger, rid, **kwargs) as client:
        ctx = Context(client=client, run_id=rid, private_dir=private_dir, fixture=fixture, p2_fixtures=p2_fixtures)
        ctx.state["doc_example_mode"] = doc_example_mode
        for spec in specs:
            res = CaseResult(spec.case_id, spec.title, spec.area, spec.expected, list(spec.doc_refs))
            results.append(res)
            if halted:
                res.notes.append(f"Not executed: run halted ({halted})")
                continue
            if ledger.phase_remaining(phase) < _planned(spec):
                res.notes.append(f"Not executed: needs {_planned(spec)} request(s), "
                                 f"{ledger.phase_remaining(phase)} left in phase {phase} budget")
                continue
            missing = [d for d in spec.depends_on if d in {r.case_id for r in results}
                       and next(r for r in results if r.case_id == d).classification == NOT_TESTED]
            if missing:
                res.notes.append(f"Not executed: prerequisite(s) not executed: {', '.join(missing)}")
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
        "phase": phase,
        "batch": batch,
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
        "p2_fixtures": {k: (v.describe() if hasattr(v, "describe") else v) for k, v in p2_fixtures.items()},
        "phase_est_usd_after_run": round(ledger.phase_est_usd(phase), 4),
        "listening_queue": ctx.listening,
        "cases": [r.to_dict(secrets) for r in results],
    }
    serialized = scrub_paths(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    assert_no_secret(serialized, settings)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "results.json").write_text(serialized + "\n", encoding="utf-8")
    summary = render_run_summary(payload)
    assert_no_secret(summary, settings)
    (run_dir / "summary.md").write_text(summary, encoding="utf-8")
    if ctx.listening:
        from .listening import write_listening_pack

        write_listening_pack(rid, ctx.listening, private_dir, settings.evidence_dir.parent / "reports" / "listening")
    return run_dir


def render_run_summary(payload: dict) -> str:
    lines = [
        f"# Run {payload['run_id']}" + (f" (phase {payload.get('phase')}, batch {payload.get('batch')})"
                                        if payload.get("phase", 1) >= 2 else ""),
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
