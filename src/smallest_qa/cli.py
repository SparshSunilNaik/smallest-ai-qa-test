"""Command line entry point.

  smallest-qa plan                       # offline: matrix, request + cost estimate, key status
  smallest-qa check-key                  # offline: reports configured yes/no, never the value
  smallest-qa make-fixtures              # offline: generate the STT WAV with macOS `say`
  smallest-qa run --approve-live [...]   # LIVE: executes bounded, sequential, budgeted cases
  smallest-qa report                     # offline: aggregate evidence into reports/results-summary.md
"""

from __future__ import annotations

import argparse
import sys

from .cases import CASES
from .config import REPO_ROOT, load_settings
from .fixtures import STT_REFERENCE_TEXT, ensure_stt_fixture
from .runner import execute, ledger_for, select_cases

# Rough public list prices (smallest.ai/pricing, voice-agent layer figures, fetched 2026-11-22).
TTS_USD_PER_MIN = 0.09
STT_USD_PER_MIN = 0.009
CHARS_PER_SECOND = 14.0  # rough speaking rate used only to convert characters into audio minutes
FIXTURE_SECONDS_ESTIMATE = 6.0


def _estimate(specs) -> dict:
    reqs = sum(s.planned_requests for s in specs)
    chars = sum(s.synth_chars for s in specs)
    stt_reqs = sum(s.stt_audio_requests for s in specs)
    tts_min = chars / CHARS_PER_SECOND / 60
    stt_min = stt_reqs * FIXTURE_SECONDS_ESTIMATE / 60
    return {"requests": reqs, "synth_chars": chars, "tts_audio_min": tts_min, "stt_requests_with_audio": stt_reqs,
            "stt_audio_min": stt_min, "usd": tts_min * TTS_USD_PER_MIN + stt_min * STT_USD_PER_MIN}


def cmd_plan(args) -> int:
    settings = load_settings()
    ledger = ledger_for(settings)
    specs = select_cases(args.only.split(",") if args.only else None, args.include_optional)
    print(f"API key configured: {'yes' if settings.key_configured else 'NO (see README: paste into .env)'}")
    print(f"Cumulative request budget: used {ledger.used} / cap {ledger.max_requests} "
          f"(remaining {ledger.remaining})\n")
    print(f"{'ID':<8} {'Area':<15} {'Req':>3}  {'Provenance':<12} Title")
    for s in CASES:
        mark = "" if s in specs else "  [not selected" + (": optional, use --include-optional]" if s.optional else "]")
        print(f"{s.case_id:<8} {s.area:<15} {s.planned_requests:>3}  {s.requirement:<12} {s.title}{mark}")
    est = _estimate(specs)
    print(f"\nSelected cases: {len(specs)}  planned requests: {est['requests']} "
          f"(cap remaining after: {ledger.remaining - est['requests']})")
    print(f"Synthesised characters (success paths): {est['synth_chars']} "
          f"~ {est['tts_audio_min']:.2f} audio-min TTS")
    print(f"STT requests carrying audio: {est['stt_requests_with_audio']} "
          f"~ {est['stt_audio_min']:.2f} audio-min")
    print(f"Rough list-price cost: ~${est['usd']:.3f} USD (voice-agent layer prices; per-API credit cost is not "
          "documented; rejected 4xx billing is not documented)")
    if ledger.remaining < est["requests"]:
        print("\nWARNING: selection exceeds remaining cumulative budget; later cases will be skipped.")
    return 0


def cmd_check_key(_args) -> int:
    s = load_settings()
    print(f"SMALLEST_API_KEY configured: {'yes' if s.key_configured else 'no'}")
    return 0 if s.key_configured else 1


def cmd_make_fixtures(_args) -> int:
    fx = ensure_stt_fixture()
    print(f"STT fixture ready: {fx.path.relative_to(REPO_ROOT)}  {fx.duration_s:.2f}s  sha256={fx.sha256[:16]}...")
    print(f"Reference text: {STT_REFERENCE_TEXT}")
    return 0


def cmd_run(args) -> int:
    settings = load_settings()
    if not args.approve_live:
        print("Refusing to make live API requests without --approve-live. Run `smallest-qa plan` first.")
        return 2
    if not settings.key_configured:
        print("SMALLEST_API_KEY is not configured. Paste it into .env (see README).")
        return 2
    specs = select_cases(args.only.split(",") if args.only else None, args.include_optional)
    ledger = ledger_for(settings)
    print(f"Live run: {len(specs)} case(s); ledger {ledger.used}/{ledger.max_requests} used before run")
    run_dir = execute(settings, specs)
    print(f"\nEvidence: {run_dir.relative_to(REPO_ROOT)}/results.json and summary.md")
    print(f"Ledger after run: {ledger.used}/{ledger.max_requests}")
    return 0


def cmd_report(_args) -> int:
    from .report import render

    settings = load_settings()
    ledger = ledger_for(settings)
    out = REPO_ROOT / "reports" / "results-summary.md"
    out.write_text(render(settings.evidence_dir, ledger.used, ledger.max_requests), encoding="utf-8")
    print(f"Wrote {out.relative_to(REPO_ROOT)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="smallest-qa", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "run"):
        p = sub.add_parser(name)
        p.add_argument("--only", help="comma-separated case ids, e.g. TTS-01,STT-01")
        p.add_argument("--include-optional", action="store_true", help="include opt-in cases (TTS-08)")
        if name == "run":
            p.add_argument("--approve-live", action="store_true", help="required: confirms live, billable requests")
    sub.add_parser("check-key")
    sub.add_parser("make-fixtures")
    sub.add_parser("report")
    args = parser.parse_args(argv)
    handlers = {"plan": cmd_plan, "run": cmd_run, "check-key": cmd_check_key, "make-fixtures": cmd_make_fixtures,
                "report": cmd_report}
    return handlers[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
