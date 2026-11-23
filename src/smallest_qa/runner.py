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
from .config import (BATCH_REQUEST_CAPS, CLOSED_PHASES, MAX_BATCH_REQUESTS, PHASE_REQUEST_CAPS, PHASE_USD_CAPS,
                     Settings)
from .fixtures import ensure_stt_fixture
from .redact import redact_text, scrub_paths
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
                         phase_caps=PHASE_REQUEST_CAPS, phase_usd_caps=PHASE_USD_CAPS,
                         closed_phases=CLOSED_PHASES if settings.enforce_closed_phases else frozenset(),
                         batch_caps=BATCH_REQUEST_CAPS)


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
    roots = {str(s.batch).split("-")[0] for s in specs}
    for root in roots:
        bcap = BATCH_REQUEST_CAPS.get((phase, root))
        if bcap is not None:
            used = sum(1 for e in ledger.entries() if ledger.phase_of(e) == phase
                       and str(e.get("batch", "")).split("-")[0] == root)
            if used + need > bcap:
                problems.append(f"batch {root}: {used} used + {need} planned exceeds its cap of {bcap}")
    if phase in ledger.closed_phases:
        problems.append(f"phase {phase} is closed")
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

    console_lines: list[str] = []
    user_log = log

    def log(msg: str = "") -> None:  # noqa: F811 - tee every console line into a redacted per-run console.log
        user_log(msg)
        console_lines.append(str(msg))
        try:
            _append_console(run_dir, str(msg), settings)
        except Exception as exc:  # noqa: BLE001 - logging must never abort a run
            user_log(f"  warning: console.log write failed: {type(exc).__name__}")

    log(f"run {rid} phase {phase} batch {batch or '-'}: {len(specs)} case(s); ledger {ledger_for(settings).used} "
        f"before run")
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
            cp = _checkpoint(run_dir, len(results), res, client.secrets, settings)
            log(f"  checkpoint: {cp.relative_to(run_dir) if cp else 'FAILED'}")

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
        "cases": [_case_dict(r, secrets) for r in results],
    }
    serialized = scrub_paths(redact_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), secrets))
    assert_no_secret(serialized, settings)
    run_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write(run_dir / "results.json", serialized + "\n")
    summary = render_run_summary(payload)
    assert_no_secret(summary, settings)
    _atomic_write(run_dir / "summary.md", summary)
    log(f"results.json and summary.md written; ledger {ledger.used} after run")
    # Per-case checkpoints are deliberately never deleted: they are the durable record if anything above fails.
    if ctx.listening:
        from .listening import write_listening_pack

        write_listening_pack(rid, ctx.listening, private_dir, settings.evidence_dir.parent / "reports" / "listening")
    return run_dir


CHECKPOINT_DIR = "checkpoints"


def _atomic_write(path: Path, text: str) -> None:
    """Write via a temp file in the same directory + fsync + os.replace: readers see old or new, never partial."""
    import os
    import tempfile

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _append_console(run_dir: Path, msg: str, settings: Settings) -> None:
    line = scrub_paths(redact_text(msg, (settings.api_key,) if settings.api_key else ()))
    assert_no_secret(line, settings)
    with (run_dir / "console.log").open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
        fh.flush()


def _case_dict(res: CaseResult, secrets: tuple[str, ...]) -> dict:
    """Serialize one case; a serialization bug must never discard the evidence of the other cases."""
    try:
        return res.to_dict(secrets)
    except Exception as exc:  # noqa: BLE001 - fall back to a minimal, still-redacted record
        return {"case_id": res.case_id, "title": res.title, "classification": res.classification,
                "serialization_error": f"{type(exc).__name__}: {redact_text(str(exc), secrets)}",
                "notes": [redact_text(str(n), secrets) for n in res.notes],
                "metrics": json.loads(json.dumps(res.metrics, default=str)) if res.metrics else {},
                "requests": [{"ledger_seq": ex.seq, "status": ex.status, "duration_ms": ex.duration_ms,
                              "response_bytes": len(ex.body or b"")} for ex in res.exchanges]}


def _checkpoint(run_dir: Path, index: int, res: CaseResult, secrets: tuple[str, ...],
                settings: Settings) -> Path | None:
    """Write each finished case to its own redacted checkpoint file, atomically, as soon as the case ends.
    Redaction (known secrets + token patterns) and path scrubbing happen before anything touches disk, and
    assert_no_secret is a final backstop. A failure here is reported and never affects other checkpoints."""
    try:
        text = scrub_paths(redact_text(json.dumps(_case_dict(res, secrets), indent=2, ensure_ascii=False,
                                                  default=str), secrets))
        assert_no_secret(text, settings)
        path = run_dir / CHECKPOINT_DIR / f"{index:02d}-{res.case_id}.json"
        _atomic_write(path, text + "\n")
        return path
    except Exception as exc:  # noqa: BLE001 - checkpointing must not abort the run
        print(f"  warning: checkpoint failed for {res.case_id}: {type(exc).__name__}")
        return None


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
        # .get(): fallback records (serialization_error) carry only a minimal request summary
        statuses = ", ".join(str(r.get("status")) for r in c["requests"]) or "-"
        durs = ", ".join(str(r.get("duration_ms")) for r in c["requests"]) or "-"
        ttfb = ", ".join(str(r.get("ttfb_ms")) for r in c["requests"]) or "-"
        failed = "; ".join(f"{k['name']} (expected {k['expected']}, got {k['actual']})"
                           for k in c.get("checks", []) if k["passed"] is False) or "-"
        if c.get("serialization_error"):
            failed = f"serialization error: {c['serialization_error']}"
        if len(c["requests"]) > 3:
            durs, ttfb = f"see results.json ({len(c['requests'])} samples)", "-"
        lines.append(f"| {c['case_id']} | {c['classification']} | {statuses} | {durs} | {ttfb} | "
                     f"{failed.replace('|', '/')} |")
    lines.append("")
    return "\n".join(lines)
