"""Command line entry point.

  smallest-qa plan                       # offline: matrix, request + cost estimate, key status
  smallest-qa check-key                  # offline: reports configured yes/no, never the value
  smallest-qa make-fixtures              # offline: generate the STT WAV with macOS `say`
  smallest-qa run --approve-live [...]   # LIVE: executes bounded, sequential, budgeted cases
  smallest-qa report                     # offline: aggregate evidence into reports/results-summary.md
"""

from __future__ import annotations

import argparse
from pathlib import Path
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


def _p2_specs(args):
    from .cases_p2 import P2_BY_ID, batch_cases

    if args.only:
        ids = [i.strip().upper() for i in args.only.split(",")]
        unknown = [i for i in ids if i not in P2_BY_ID]
        if unknown:
            raise SystemExit(f"Unknown Phase 2 case id(s): {unknown}")
        return [P2_BY_ID[i] for i in ids]
    if not args.batch:
        raise SystemExit("Phase 2 requires --batch N (or --only IDS)")
    return batch_cases(args.batch)


def cmd_plan_p2(args) -> int:
    from .budget import estimate_usd
    from .cases_p2 import BATCHES, batch_cases, planned

    settings = load_settings()
    ledger = ledger_for(settings)
    print(f"API key configured: {'yes' if settings.key_configured else 'NO'}")
    print(f"Ledger: {ledger.used} total | phase 1 {ledger.phase_used(1)}/28 (closed) | phase 2 "
          f"{ledger.phase_used(2)}/100 used, est. ${ledger.phase_est_usd(2):.3f} of $2.00\n")
    batches = [args.batch] if args.batch else BATCHES
    grand_req = grand_usd = 0.0
    for b in batches:
        if b == "3h" and not args.batch:
            print("== Batch 3h (ALTERNATIVE to Batch 3, same 15 requests): 10 synthetic + 5 human recordings")
            for s_ in batch_cases(b):
                print(f"   {s_.case_id:<11} {s_.priority:<3} {planned(s_):>2}  {s_.requirement:<11} {s_.title}")
            continue
        specs = batch_cases(b)
        req = sum(planned(s) for s in specs)
        chars = sum(s.synth_chars for s in specs)
        stt = sum(s.stt_audio_seconds for s in specs)
        usd = estimate_usd(chars, stt)
        grand_req += req
        grand_usd += usd
        print(f"== Batch {b}: {len(specs)} cases, {req} requests, ~{chars} TTS chars, ~{stt:.0f}s STT audio, "
              f"~${usd:.3f}")
        for s in specs:
            flag = " [human listening]" if s.requires_human else ""
            print(f"   {s.case_id:<11} {s.priority:<3} {planned(s):>2}  {s.requirement:<11} {s.title}{flag}")
    print(f"\nTotal planned: {int(grand_req)} requests, ~${grand_usd:.2f} list price; reserve "
          f"{100 - int(grand_req)} requests for reproduction.")
    return 0


def cmd_plan(args) -> int:
    if getattr(args, "phase", 1) == 2:
        return cmd_plan_p2(args)
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
    if args.phase == 2:
        from .runner import check_batch

        specs = _p2_specs(args)
        problems = check_batch(settings, specs, 2)
        if problems:
            print("Refusing:", "; ".join(problems))
            return 2
        ledger = ledger_for(settings)
        print(f"Phase 2 batch {args.batch or 'adhoc'}: {len(specs)} case(s); phase 2 ledger "
              f"{ledger.phase_used(2)}/100 before run")
        run_dir = execute(settings, specs, phase=2, batch=args.batch or "repro")
        print(f"\nEvidence: {run_dir.relative_to(REPO_ROOT)}/results.json and summary.md")
        print(f"Phase 2 ledger after run: {ledger.phase_used(2)}/100; est. ${ledger.phase_est_usd(2):.3f}")
        return 0
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


def cmd_sdk_compat(_args) -> int:
    import json
    import logging

    from .sdk_tools import offline_checks

    logging.disable(logging.WARNING)
    settings = load_settings()
    res = offline_checks(settings.evidence_dir)
    out_dir = settings.evidence_dir / "offline"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "sdk-compat.json"
    path.write_text(json.dumps(res, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    print(f"Wrote {path.relative_to(REPO_ROOT)} ({len(res['replays'])} recorded error bodies replayed)")
    return 0


def cmd_record(args) -> int:
    from .human import record_session

    ids = [i.strip().upper() for i in args.prompt.split(",")] if args.prompt else None
    saved = record_session(ids)
    print(f"\n{len(saved)} clip(s) saved locally. Nothing was uploaded. Review: uv run smallest-qa human list")
    return 0


def cmd_human(args) -> int:
    from .human import PROMPTS_BY_ID, delete_clip, load_clip, set_approval, set_reference, summary_rows

    ids = [i.strip().upper() for i in (args.ids or "").split(",") if i.strip()]
    for i in ids:
        if i not in PROMPTS_BY_ID:
            raise SystemExit(f"unknown clip id {i}")
    if args.action == "list":
        for r in summary_rows():
            print(f"{r['clip']}  {r['category']:<40} recorded={'yes' if r['recorded'] else 'no ':<3} "
                  f"dur={r['duration_s'] or '-':<6} ref_edited={r['reference_edited'] or False!s:<5} "
                  f"approved={'YES' if r['approved'] else 'no'}"
                  f"{' (STALE: re-recorded after approval)' if r['stale_approval'] else ''}"
                  f"{' share_transcript' if r['share_transcript'] else ''}")
        return 0
    if not ids:
        raise SystemExit("give clip ids, e.g. H1,H2")
    for i in ids:
        if not load_clip(i):
            raise SystemExit(f"{i} has not been recorded")
        if args.action == "approve":
            m = set_approval(i, True, args.share_transcript)
            print(f"{i}: approved for sending to Smallest AI (bound to sha256 {m['approved_sha256'][:12]}...)"
                  f"{'; transcript may appear in committed evidence' if args.share_transcript else ''}")
        elif args.action == "revoke":
            set_approval(i, False)
            print(f"{i}: approval revoked")
        elif args.action == "delete":
            delete_clip(i)
            print(f"{i}: deleted from disk")
        elif args.action == "review":
            from .human_review import review

            if not args.run:
                raise SystemExit("review needs --run <run_id>, e.g. --run 20261122T174926Z")
            review(i, args.run, load_settings().evidence_dir)
        elif args.action == "edit-reference":
            text = input(f"New reference transcript for {i}: ").strip()
            if text:
                set_reference(i, text)
                print(f"{i}: reference updated (approval unchanged; audio unchanged)")
    return 0


def cmd_human_eval(args) -> int:
    import json

    from .human_eval import evaluate_run
    from .redact import scrub_paths

    settings = load_settings()
    detail, public = evaluate_run(settings.evidence_dir, args.run)
    priv = settings.evidence_dir / "private" / args.run / "human-eval-detail.json"
    priv.write_text(json.dumps(detail, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    pub = settings.evidence_dir / "offline" / f"human-eval-{args.run}.json"
    if args.revision or pub.exists():
        n = 1
        while (pub.parent / f"human-eval-{args.run}-rev{n}.json").exists():
            n += 1
        pub = pub.parent / f"human-eval-{args.run}-rev{n}.json"
        public["revision"] = n
        public["revision_note"] = "recomputed offline after speaker reference review; no API request"
    text = scrub_paths(json.dumps(public, indent=2, ensure_ascii=False, default=str))
    for pid, clip in detail["clips"].items():  # fail closed: unshared human text must never reach committed output
        if not public["clips"][pid].get("transcript_shared"):
            for t in {clip["reference"], clip["hypothesis"]}:
                if t and t in text:
                    raise SystemExit(f"refusing to write: {pid} text would leak into committed evidence")
    pub.write_text(text + "\n", encoding="utf-8")
    print(f"private detail: {priv.relative_to(REPO_ROOT)} (git-ignored)\ncommitted summary: {pub.relative_to(REPO_ROOT)}")
    return 0


def cmd_q6(args) -> int:
    import json

    from .q6_analysis import analyze

    settings = load_settings()
    res = analyze(settings.evidence_dir, args.run, REPO_ROOT / "fixtures" / "audio" / "p2" / "gap_1500ms.wav")
    out = settings.evidence_dir / "offline" / f"q6-timestamp-analysis-{args.run}.json"
    out.write_text(json.dumps(res, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k not in ("grid", "interpretation")}, indent=1))
    print(f"Wrote {out.relative_to(REPO_ROOT)}")
    return 0


def cmd_sse_replay(args) -> int:
    import json

    from .sdk_tools import replay_live_sse

    settings = load_settings()
    wire = (settings.evidence_dir / "private" / args.run / "P2-SDK-02-wire.sse").read_bytes()
    res = {"source_run": args.run, "source_case": "P2-SDK-02", **replay_live_sse(wire)}
    out = settings.evidence_dir / "offline" / f"sdk-sse-live-replay-{args.run}.json"
    out.write_text(json.dumps(res, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "terminal_frames"}, indent=1, default=str))
    print(f"Wrote {out.relative_to(REPO_ROOT)}")
    return 0


def cmd_docs_offline(_args) -> int:
    import json
    import tempfile

    from .doc_examples import offline_suite

    settings = load_settings()
    with tempfile.TemporaryDirectory() as tmp:
        res = offline_suite(settings.evidence_dir, Path(tmp))
    out = settings.evidence_dir / "offline" / "doc-examples-offline.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for r in res:
        print(f"{r['example']:36} exit={r['exit_code']} files={[f['starts_as'] for f in r['files']]} "
              f"api_calls={sum(1 for c in r['calls'] if c.get('host_kind') == 'api')}")
    print(f"Wrote {out.relative_to(REPO_ROOT)}")
    return 0


def cmd_matrix_p2(_args) -> int:
    from .budget import estimate_usd
    from .cases_p2 import BATCHES, batch_cases, planned

    short = {"https://docs.smallest.ai/": "", "https://github.com/smallest-inc/": "gh:"}

    def src(u: str) -> str:
        for k, v in short.items():
            u = u.replace(k, v)
        return u

    lines = ["# Phase 2 test matrix", "",
             "Generated from `src/smallest_qa/cases_p2.py` by `uv run smallest-qa matrix-p2`; do not edit by hand.",
             "Doc links are relative to `https://docs.smallest.ai/` unless prefixed `gh:` (github.com/smallest-inc).",
             "Provenance: **documented** deviations can become defects after reproduction; **quality** and "
             "**exploratory** are observations only. 🎧 = audio queued for human listening.", ""]
    for b in BATCHES:
        specs = batch_cases(b)
        req = sum(planned(x) for x in specs)
        usd = estimate_usd(sum(x.synth_chars for x in specs), sum(x.stt_audio_seconds for x in specs))
        lines += [f"## Batch {b} ({req} requests, est. ${usd:.3f})", "",
                  "| ID | Pri | Area | Test | Provenance | Documented / expected behaviour | Source | Req |",
                  "|---|---|---|---|---|---|---|---|"]
        for x in specs:
            lines.append(f"| {x.case_id} | {x.priority} | {x.area} | {x.title}{' 🎧' if x.requires_human else ''} | "
                         f"{x.requirement} | {x.expected.replace('|', '/')} | "
                         f"{'<br>'.join(src(u) for u in x.doc_refs)} | {planned(x)} |")
        lines.append("")
    out = REPO_ROOT / "docs" / "phase2-test-matrix.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out.relative_to(REPO_ROOT)}")
    return 0


def cmd_fixtures_p2(_args) -> int:
    from .fixtures_p2 import build_all

    for k, v in build_all().items():
        print(f"{k:24} " + (v if isinstance(v, str) else f"{v.duration_s:5.2f}s {v.sample_rate} Hz "
                                                          f"sha256={v.sha256[:12]}"))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="smallest-qa", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "run"):
        p = sub.add_parser(name)
        p.add_argument("--only", help="comma-separated case ids, e.g. TTS-01,STT-01")
        p.add_argument("--include-optional", action="store_true", help="include opt-in cases (TTS-08)")
        p.add_argument("--phase", type=int, default=1, choices=(1, 2))
        p.add_argument("--batch", help="Phase 2 batch number (1-6); at most 20 requests each")
        if name == "run":
            p.add_argument("--approve-live", action="store_true", help="required: confirms live, billable requests")
    sub.add_parser("check-key")
    sub.add_parser("make-fixtures")
    sub.add_parser("report")
    sub.add_parser("sdk-compat", help="offline: replay recorded error bodies into the official SDK")
    sub.add_parser("fixtures-p2", help="offline: generate Phase 2 STT fixtures with macOS say")
    sub.add_parser("docs-offline", help="offline: run saved docs examples against recorded responses")
    sub.add_parser("matrix-p2", help="offline: regenerate docs/phase2-test-matrix.md from the catalogue")
    rec = sub.add_parser("record", help="LOCAL ONLY: record human STT clips with your microphone")
    rec.add_argument("--prompt", help="comma-separated prompt ids (default H1-H5)")
    hp = sub.add_parser("human", help="manage local human clips (list/approve/revoke/delete/edit-reference)")
    hp.add_argument("action", choices=("list", "approve", "revoke", "delete", "edit-reference", "review"))
    hp.add_argument("--run", help="with review: the run whose saved STT response to compare against")
    hp.add_argument("ids", nargs="?", help="comma-separated clip ids, e.g. H1,H3")
    hp.add_argument("--share-transcript", action="store_true",
                    help="with approve: allow the reference and Smallest's transcript in committed evidence")
    he = sub.add_parser("human-eval", help="offline: WER/CER analysis of a Batch 3h run (no API requests)")
    he.add_argument("--run", required=True)
    he.add_argument("--revision", action="store_true",
                    help="write a new numbered revision instead of the original summary file")
    q6 = sub.add_parser("q6", help="offline: word timestamps vs waveform for P2-STT-15")
    q6.add_argument("--run", required=True)
    rp = sub.add_parser("sse-replay", help="offline: replay recorded live SSE wire bytes into the SDK")
    rp.add_argument("--run", required=True)
    args = parser.parse_args(argv)
    handlers = {"plan": cmd_plan, "run": cmd_run, "check-key": cmd_check_key, "make-fixtures": cmd_make_fixtures,
                "report": cmd_report, "sdk-compat": cmd_sdk_compat, "fixtures-p2": cmd_fixtures_p2,
                "docs-offline": cmd_docs_offline, "matrix-p2": cmd_matrix_p2,
                "sse-replay": cmd_sse_replay, "record": cmd_record, "human": cmd_human,
                "human-eval": cmd_human_eval, "q6": cmd_q6}
    return handlers[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
