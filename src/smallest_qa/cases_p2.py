"""Phase 2 case catalogue: broader, real-world API behaviour.

Provenance rules (unchanged from Phase 1):
- DOCUMENTED checks can become confirmed defects (after reproduction in a separate run).
- QUALITY / EXPLORATORY checks are observations only.
- Anything about how speech *sounds* (pronunciation, accent, naturalness) is never asserted by machine;
  such clips are queued for human listening (`requires_human`). TTS->STT round trips are labelled as a
  machine proxy that conflates TTS and STT behaviour.
"""

from __future__ import annotations

import json
import logging
import random
import re
import statistics
from collections.abc import Callable
from typing import Any

from . import api
from . import docs_refs as D
from .audio import (AudioFormatError, analyze_pcm16, looks_like_mp3, mulaw_to_pcm16, parse_wav, pcm16_to_wav)
from .cases import (SHORT_EN, CaseResult, CaseSpec, Context, _error_shape, _no_audio)
from .client import Exchange
from .contract import conformance, human_message, signature, undocumented_fields
from .results import (CANDIDATE, DOC_AMBIGUITY, DOCUMENTED, EXPECTED, EXPLORATORY, INCONCLUSIVE, NOT_TESTED, PASSED,
                      QUALITY, auto_classify)
from .stats import summarize
from .textsim import char_error_rate, key_token_hits, normalize, word_error_rate

V31_VOICES_PATH = "/waves/v1/lightning-v3.1/get_voices"
D_V31_CARD = "https://docs.smallest.ai/model-cards/text-to-speech/lightning-v-3-1"
D_WS = "https://docs.smallest.ai/api-reference/models/text-to-speech/tts"
D_MATH = "https://docs.smallest.ai/models/text-to-speech/math-notation"
D_BEST = "https://docs.smallest.ai/models/text-to-speech/best-practices"
D_TTS_QS = "https://docs.smallest.ai/models/text-to-speech/quickstart"
D_LANGDET = "https://docs.smallest.ai/models/speech-to-text/features/language-detection"
D_PULSE_PRO_CARD = "https://docs.smallest.ai/model-cards/speech-to-text/pulse-pro"
D_COOKBOOK = "https://github.com/smallest-inc/cookbook/blob/main/speech-to-text/transcribe-python.py"

T_250 = ("Thank you for calling Horizon Bank. Your recent payment has been received, and your account is now up "
         "to date. If you would like to hear your balance, please stay on the line, and an agent will help you "
         "shortly with any other questions.")
T_140 = "Your order has shipped and should arrive by Thursday. Reply to this message if you need to change the address."
T_20 = "Hello, how are you?"
T_500 = (T_250 + " We also wanted to let you know about our new savings plan, which offers a higher interest rate "
         "for customers who keep a minimum balance for twelve months. You can sign up through the mobile app or "
         "at any branch, and there are no extra fees to get started.")
T_1000 = (T_500 + " Our branches are open from nine in the morning until five in the evening on weekdays, and from "
          "ten until two on Saturdays. For security reasons, we will never ask for your password or one time code "
          "over the phone, so please do not share them with anyone. If you notice any unusual activity, contact "
          "our support team immediately. The final sentence mentions a purple elephant named Gopal.")
TTS_INTEGRITY_SR = 24000


# ============================================================================= shared helpers

def _contract_checks(res: CaseResult, ex: Exchange, product: str, *, documented: bool = True) -> None:
    body = ex.json()
    ok, problems = conformance(body, product)
    doc = D.TTS_SYNC if product == "tts" else D.STT_TRANSCRIBE
    res.check(f"error body conforms to the documented {product.upper()} error schema", ok,
              "documented field types + a human-readable message string", "; ".join(problems) or "conforms",
              DOCUMENTED if documented else QUALITY, doc)
    res.metrics.setdefault("error_contract", []).append({
        "status": ex.status, "signature": signature(body), "undocumented_fields": undocumented_fields(body, product),
        "human_message": human_message(body)})


def _rejected(res: CaseResult, ex: Exchange, product: str, *, documented_400: bool, doc: str,
              documented_contract: bool = True) -> None:
    s = ex.status
    res.check("rejected with a 4xx client error", s is not None and 400 <= s < 500, "4xx", s,
              DOCUMENTED if documented_400 else QUALITY, doc)
    if documented_400:
        res.check("status is the documented 400", s == 400, "400", s, DOCUMENTED, doc)
    _contract_checks(res, ex, product, documented=documented_contract)
    _no_audio(res, ex)


def _tts_integrity(ctx: Context, res: CaseResult, ex: Exchange, text: str, *, sample_rate: int = TTS_INTEGRITY_SR,
                   label: str = "", listen_focus: str = "") -> bytes | None:
    """Machine-verifiable audio integrity for a sync WAV response. Returns PCM or None."""
    p = f"{label}: " if label else ""
    res.check(f"{p}HTTP 200", ex.status == 200, "200", ex.status, DOCUMENTED, D.TTS_SYNC)
    try:
        info = parse_wav(ex.body)
    except AudioFormatError as exc:
        res.check(f"{p}valid RIFF/WAVE", False, "RIFF/WAVE", str(exc), DOCUMENTED, D.TTS_SYNC)
        return None
    res.check(f"{p}WAV sample rate equals requested", info.sample_rate == sample_rate, sample_rate,
              info.sample_rate, DOCUMENTED, D.TTS_SYNC)
    pcm = ex.body[info.data_offset: info.data_offset + info.data_bytes]
    a = analyze_pcm16(pcm, info.sample_rate)
    cps = len(text) / a["duration_s"] if a.get("duration_s") else None
    res.check(f"{p}audio not silent", not a.get("all_silent", True), "speech energy present",
              f"rms {a.get('rms_dbfs')} dBFS", QUALITY)
    res.check(f"{p}no clipping (<0.1% samples at full scale)", a.get("clipped_fraction", 1) < 0.001, "< 0.001",
              a.get("clipped_fraction"), QUALITY)
    res.check(f"{p}no internal silence > 2 s (dropped content heuristic)",
              (a.get("longest_internal_silence_ms") or 0) <= 2000, "<= 2000 ms",
              a.get("longest_internal_silence_ms"), QUALITY)
    res.check(f"{p}speaking rate plausible (5-30 chars/s)", cps is not None and 5 <= cps <= 30, "5-30",
              None if cps is None else round(cps, 1), QUALITY)
    res.metrics[f"{label or 'audio'}_integrity"] = {**a, "chars": len(text), "chars_per_s": cps and round(cps, 2)}
    name = f"{res.case_id}{('-' + label) if label else ''}.wav"
    ctx.save_private(name, ex.body)
    ctx.listening.append({"clip": name, "case_id": res.case_id, "text": text, "focus": listen_focus})
    return pcm


def _transcribe(ctx: Context, case_id: str, audio: bytes, language: str = "en", model: str = "pulse",
                **params: str) -> tuple[Exchange, dict | None]:
    ex = api.transcribe(ctx.client, case_id, audio, {"model": model, "language": language, **params})
    body = ex.json()
    return ex, body if isinstance(body, dict) else None


def _roundtrip(ctx: Context, res: CaseResult, wav: bytes, text: str, language: str,
               groups: list[list[str]], absent: list[str] = (), numeric: bool = False) -> None:
    """TTS->STT machine proxy. EXPLORATORY: STT errors and TTS errors cannot be separated here."""
    ex, body = _transcribe(ctx, res.case_id, wav, language)
    res.exchanges.append(ex)
    res.check("round-trip STT HTTP 200", ex.status == 200, "200", ex.status, DOCUMENTED, D.STT_TRANSCRIBE)
    tx = (body or {}).get("transcription") if body else None
    if not isinstance(tx, str):
        return
    hits = key_token_hits(tx, groups)
    res.metrics["roundtrip"] = {"transcription": tx, "key_tokens": hits,
                                "wer_vs_input_text": round(word_error_rate(text, tx), 3),
                                "note": "machine proxy only; not a pronunciation judgement"}
    res.check("round-trip: expected spoken items recovered", hits["hit"] == hits["total"], f"{hits['total']} items",
              f"{hits['hit']} found; missing {hits['missing']}", EXPLORATORY)
    if numeric:
        from collections import Counter

        from .wer import canonical_numbers

        want, got = Counter(canonical_numbers(text)), Counter(canonical_numbers(tx))
        missing = list((want - got).elements())
        res.metrics["roundtrip"]["numeric"] = {"input": canonical_numbers(text), "transcript": canonical_numbers(tx),
                                               "missing": missing}
        res.check("round-trip: numeric/currency values recovered (canonical, format-independent)", not missing,
                  [f"{v} {u}".strip() for v, u in want.elements()], missing or "all recovered", EXPLORATORY)
    if absent:
        words = set(normalize(tx))
        leaked = [a for a in absent if a in words]
        res.check("round-trip: no unexpected spoken tokens", not leaked, f"none of {list(absent)}", leaked or "none",
                  EXPLORATORY)


# ============================================================================= Batch 1: F2 reassessment

def _voice_ids(ctx: Context, res: CaseResult, path: str, state_key: str) -> None:
    ex = ctx.client.request(res.case_id, "GET", path)
    res.exchanges.append(ex)
    res.check("HTTP 200", ex.status == 200, "200", ex.status, DOCUMENTED, D.DEPRECATIONS)
    body = ex.json()
    ids = sorted(api.extract_voice_ids(body)) if body is not None else []
    ctx.state[state_key] = set(ids) if body is not None else None
    res.check("catalogue parses to voice ids", bool(ids), "> 0 ids", len(ids), QUALITY)
    res.metrics.update({"voice_count": len(ids), "voice_ids": ids})  # public catalogue data, no secrets


def f2_pro_catalogue(ctx: Context, res: CaseResult) -> None:
    _voice_ids(ctx, res, api.PRO_VOICES_PATH, "pro_ids")


def f2_v31_catalogue(ctx: Context, res: CaseResult) -> None:
    _voice_ids(ctx, res, V31_VOICES_PATH, "v31_ids")
    res.notes.append("Legacy route, documented as retiring 2026-11-30 18:30 UTC; used only to isolate F2.")


def _pick(ctx: Context) -> dict[str, str | None]:
    pro, v31 = ctx.state.get("pro_ids"), ctx.state.get("v31_ids")
    if not pro or not v31:
        return {"v31_only": None, "pro_only": None}
    v31_only = sorted(v31 - pro)
    pro_only = sorted(pro - v31)
    pick_v31 = next((v for v in api.NON_PRO_VOICE_CANDIDATES if v in v31_only), v31_only[0] if v31_only else None)
    pick_pro = api.TTS_VOICE if api.TTS_VOICE in pro_only else (pro_only[0] if pro_only else None)
    ctx.state["f2_overlap_count"] = len(pro & v31)
    return {"v31_only": pick_v31, "pro_only": pick_pro}


def _f2_probe(model: str | None, which: str, expect_ok: bool) -> Callable[[Context, CaseResult], None]:
    def run(ctx: Context, res: CaseResult) -> None:
        voice = _pick(ctx)[which]
        if voice is None:
            res.notes.append(f"No {which} voice could be isolated from the two catalogues; not tested.")
            res.classification = NOT_TESTED
            return
        res.metrics.update({"voice": voice, "model_sent": model, "voice_in_pro_catalogue": voice in ctx.state["pro_ids"],
                            "voice_in_v31_catalogue": voice in ctx.state["v31_ids"]})
        body = api.tts_body("Hello, this is a voice compatibility check.", voice_id=voice, model=model)
        ex = api.synthesize(ctx.client, res.case_id, body)
        res.exchanges.append(ex)
        if expect_ok:
            _tts_integrity(ctx, res, ex, body["text"], listen_focus="voice identity matches catalogue entry")
        else:
            res.check("mismatched voice/model rejected with 400", ex.status == 400, "400", ex.status, DOCUMENTED,
                      D.CHANGELOG_2026_11_05)
            msg = human_message(ex.json()) or ""
            res.metrics["message"] = msg
            res.check("message identifies a voice/model availability problem",
                      voice in msg and "not available" in msg, "names voice + availability", msg or "<none>",
                      QUALITY)
            _contract_checks(res, ex, "tts")
    return run


# ============================================================================= Batch 1: TTS sync error contract

def _tts_bad(body: dict | None = None, *, raw: bytes | None = None, documented_400: bool = True,
             headers: dict | None = None) -> Callable[[Context, CaseResult], None]:
    def run(ctx: Context, res: CaseResult) -> None:
        if raw is not None:
            ex = ctx.client.request(res.case_id, "POST", api.TTS_PATH, content=raw,
                                    headers=headers or {"Content-Type": "application/json"})
        else:
            ex = api.synthesize(ctx.client, res.case_id, body or {})
        res.exchanges.append(ex)
        _rejected(res, ex, "tts", documented_400=documented_400, doc=D.TTS_SYNC)
    return run


def _without(key: str) -> dict:
    b = api.tts_body(SHORT_EN)
    b.pop(key)
    return b


# ============================================================================= Batch 1: SDK + docs examples

def _sdk_capture_warnings() -> tuple[logging.Handler, list[str]]:
    seen: list[str] = []

    class H(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            msg = re.sub(r"'audio': '[^']*'?", "'audio': '<omitted>'", record.getMessage().split(", sse:")[0])
            seen.append(msg[:200])

    h = H(level=logging.WARNING)
    logging.getLogger().addHandler(h)
    return h, seen


def sdk_tts(ctx: Context, res: CaseResult) -> None:
    from .sdk_tools import LedgerTransport, sdk_client

    tr = LedgerTransport(ctx.client, res.case_id, inner=ctx.client._transport)
    sdk = sdk_client(tr, ctx.client.settings.api_key, max_retries=0)
    text = "Modern problems require modern solutions."
    try:
        audio = b"".join(sdk.waves.synthesize_tts(text=text, voice_id="meher", model="lightning_v3.1_pro",
                                                  sample_rate=24000, speed=1.0, output_format="wav"))
        res.metrics["sdk_raised"] = None
    except Exception as exc:  # noqa: BLE001 - observation
        audio = b""
        res.metrics["sdk_raised"] = type(exc).__name__
    res.exchanges.extend(tr.exchanges)
    res.check("SDK call completes without exception", res.metrics["sdk_raised"] is None, "no exception",
              res.metrics["sdk_raised"] or "none", DOCUMENTED, D_TTS_QS)
    if tr.exchanges:
        fake = tr.exchanges[-1]
        fake_audio = Exchange(**{**fake.__dict__, "body": audio})
        _tts_integrity(ctx, res, fake_audio, text, label="sdk")
    res.check("SDK made exactly one HTTP attempt (max_retries=0)", len(tr.exchanges) == 1, 1, len(tr.exchanges),
              QUALITY)


def sdk_sse(ctx: Context, res: CaseResult) -> None:
    from .sdk_tools import LedgerTransport, sdk_client

    tr = LedgerTransport(ctx.client, res.case_id, inner=ctx.client._transport)
    sdk = sdk_client(tr, ctx.client.settings.api_key, max_retries=0)
    handler, warnings = _sdk_capture_warnings()
    try:
        items = list(sdk.waves.synthesize_sse_tts(text=SHORT_EN, voice_id="meher", model="lightning_v3.1_pro",
                                                  sample_rate=24000))
        raised = None
    except Exception as exc:  # noqa: BLE001
        items, raised = [], type(exc).__name__
    finally:
        logging.getLogger().removeHandler(handler)
    res.exchanges.extend(tr.exchanges)
    wire = tr.exchanges[-1] if tr.exchanges else None
    wire_audio_frames = wire.body.count(b'"audio"') if wire else 0
    if wire is not None and wire.body:
        ctx.save_private(f"{res.case_id}-wire.sse", wire.body)  # raw live SSE (contains audio) -> private only
        res.metrics["wire_sha256"] = __import__("hashlib").sha256(wire.body).hexdigest()
    res.metrics.update({"sdk_items_yielded": len(items), "sdk_raised": raised,
                        "server_audio_frames_on_wire": wire_audio_frames,
                        "sdk_warnings_sample": warnings[:3], "sdk_warning_count": len(warnings),
                        "item_types": sorted({type(i).__name__ for i in items})})
    res.check("server streamed audio frames (wire level)", wire is not None and wire.status == 200 and
              wire_audio_frames > 0, "> 0 audio frames", wire_audio_frames, DOCUMENTED, D.TTS_STREAMING)
    res.check("SDK synthesize_sse_tts yields the streamed audio", len(items) > 0, "> 0 items",
              f"{len(items)} items; {len(warnings)} 'skipping SSE event' warnings", DOCUMENTED, D_TTS_QS)


def sdk_stt(ctx: Context, res: CaseResult) -> None:
    from .sdk_tools import LedgerTransport, sdk_client

    fx = ctx.fixture
    assert fx is not None
    tr = LedgerTransport(ctx.client, res.case_id, inner=ctx.client._transport)
    sdk = sdk_client(tr, ctx.client.settings.api_key, max_retries=0)
    try:
        r = sdk.waves.speech_to_text.transcribe(model="pulse", language="en", request=fx.path.read_bytes())
        tx, raised = getattr(r, "transcription", None), None
    except Exception as exc:  # noqa: BLE001
        tx, raised = None, type(exc).__name__
    res.exchanges.extend(tr.exchanges)
    res.check("SDK transcribe returns a typed response with transcription", isinstance(tx, str) and bool(tx),
              "non-empty transcription", raised or repr(tx)[:80], DOCUMENTED, D.STT_TRANSCRIBE)
    if isinstance(tx, str):
        res.metrics["wer"] = round(word_error_rate(fx.reference_text, tx), 3)


def _doc_example(example: str, est_chars: int = 0, est_stt: float = 0.0,
                 inputs: Callable[[Context], dict[str, bytes]] | None = None) -> Callable[[Context, CaseResult], None]:
    def run(ctx: Context, res: CaseResult) -> None:
        from .doc_examples import run_example

        if ctx.state.get("doc_example_mode") == "skip":
            res.notes.append("Doc example execution disabled in this (offline test) context.")
            res.classification = NOT_TESTED
            return
        c = ctx.client
        led = c.ledger
        c.guard.check()
        c.pace()
        env = {"QA_LEDGER": str(led.path), "QA_LEDGER_MAX": str(led.max_requests), "QA_RUN_ID": c.run_id,
               "QA_CASE_ID": res.case_id, "QA_PHASE": str(c.phase), "QA_BATCH": c.batch,
               "QA_EST_CHARS": str(est_chars), "QA_EST_STT": str(est_stt)}
        workdir = ctx.private_dir / "examples" / res.case_id
        out = run_example(example, mode="live", api_key=c.settings.api_key, workdir=workdir, ledger_env=env,
                          input_files=inputs(ctx) if inputs else None)
        res.metrics["example_run"] = out.to_dict()
        for call in out.calls:
            if call.get("host_kind") != "api":
                continue
            ex = Exchange(case_id=res.case_id, seq=call.get("ledger_seq", -1), method=call["method"],
                          path=call["url_path"], params={"query": call.get("query")},
                          request_summary={"via": f"docs example {example}", "client_timeout": call.get("timeout")},
                          auth_mode="valid", started={"utc": "see example_run", "ist": "see example_run"},
                          status=call.get("status"), headers=call.get("resp_headers", {}),
                          body=(call.get("resp_excerpt") or "").encode(), duration_ms=call.get("ms"))
            c.finished(ex, expect_auth_ok=True)
            res.exchanges.append(ex)
        res.check("example exits successfully", out.exit_code == 0, "exit 0", out.exit_code, DOCUMENTED,
                  res.doc_refs[0])
        res.check("example made exactly one Smallest API call",
                  sum(1 for k in out.calls if k.get("host_kind") == "api") == 1, 1,
                  sum(1 for k in out.calls if k.get("host_kind") == "api"), QUALITY)
        wav = next((f for f in out.files if f["name"].endswith(".wav")), None)
        if example.startswith("tts"):
            res.check("output.wav is real audio (RIFF)", bool(wav) and wav["starts_as"] == "wav", "RIFF/WAVE",
                      wav, DOCUMENTED, res.doc_refs[0])
        api_calls = [k for k in out.calls if k.get("host_kind") == "api"]
        res.check("example sets a client timeout", bool(api_calls) and all(k.get("timeout") not in (None, "None")
                                                                          for k in api_calls),
                  "explicit timeout", [k.get("timeout") for k in api_calls], QUALITY)
    return run


# ============================================================================= Batch 2: SSE / STT / voices error contract

def sse_bad_voice(ctx: Context, res: CaseResult) -> None:
    ex, obs = api.stream_sse(ctx.client, res.case_id, api.tts_body(SHORT_EN, voice_id="qa_nonexistent_voice_zz9",
                                                                   output_format="pcm"))
    res.exchanges.append(ex)
    res.metrics["sse_frames"] = len(obs.frames)
    res.check("invalid voice on SSE rejected before streaming (4xx, no audio frames)",
              ex.status is not None and 400 <= ex.status < 500 and not obs.audio_chunks, "4xx, 0 frames",
              f"{ex.status}, {len(obs.audio_chunks)} audio frames", QUALITY, D.TTS_STREAMING)
    _contract_checks(res, ex, "tts", documented=False)
    res.notes.append("No SSE error schema is documented; compared against the sync TTS schema for consistency.")


def sse_no_auth(ctx: Context, res: CaseResult) -> None:
    ex = ctx.client.request(res.case_id, "POST", api.TTS_SSE_PATH, json_body=api.tts_body(SHORT_EN),
                            headers={"Accept": "text/event-stream"}, auth="none", expect_auth_ok=False)
    res.exchanges.append(ex)
    res.check("HTTP 401", ex.status == 401, "401", ex.status, DOCUMENTED, D.AUTH)
    _contract_checks(res, ex, "tts", documented=False)


def sse_empty_text(ctx: Context, res: CaseResult) -> None:
    ex, obs = api.stream_sse(ctx.client, res.case_id, api.tts_body("", output_format="pcm"))
    res.exchanges.append(ex)
    res.check("empty text on SSE rejected (4xx, no audio)", ex.status is not None and 400 <= ex.status < 500
              and not obs.audio_chunks, "4xx", ex.status, EXPLORATORY, D.TTS_STREAMING)
    if ex.status and ex.status >= 400:
        _contract_checks(res, ex, "tts", documented=False)


def _stt_bad(params: dict[str, str], audio: str = "fixture", *, auth: str = "valid", content_type: str | None = None,
             documented_400: bool = True, expect_status: int | None = None, product_doc: str = D.STT_TRANSCRIBE,
             code_expected: str | None = None) -> Callable[[Context, CaseResult], None]:
    def run(ctx: Context, res: CaseResult) -> None:
        data = (random.Random(1234).randbytes(32768) if audio == "corrupt" else ctx.fixture.path.read_bytes())  # type: ignore[union-attr]
        ex = ctx.client.request(res.case_id, "POST", api.STT_PATH, params=params, content=data,
                                headers={"Content-Type": content_type or "application/octet-stream"}, auth=auth,
                                expect_auth_ok=auth == "valid")
        res.exchanges.append(ex)
        if expect_status:
            res.check(f"HTTP {expect_status}", ex.status == expect_status, expect_status, ex.status, DOCUMENTED,
                      product_doc)
            _contract_checks(res, ex, "stt")
            return
        _rejected(res, ex, "stt", documented_400=documented_400, doc=product_doc)
        if code_expected:
            body = ex.json() or {}
            res.check(f"documented `code` value {code_expected}", isinstance(body, dict) and
                      body.get("code") == code_expected, code_expected,
                      body.get("code") if isinstance(body, dict) else None, QUALITY, D.STT_TRANSCRIBE)
    return run


def stt_probe_ok(params: dict[str, str], content_type: str, note: str) -> Callable[[Context, CaseResult], None]:
    """Exploratory: request shapes whose acceptance is undocumented/inconsistent in docs."""
    def run(ctx: Context, res: CaseResult) -> None:
        fx = ctx.fixture
        ex = ctx.client.request(res.case_id, "POST", api.STT_PATH, params=params, content=fx.path.read_bytes(),
                                headers={"Content-Type": content_type})
        res.exchanges.append(ex)
        body = ex.json()
        res.metrics.update({"status": ex.status, "signature": signature(body)})
        ok = ex.status == 200 and isinstance(body, dict) and bool(body.get("transcription"))
        res.check("accepted and transcribed", ok, "200 + transcription (behaviour not documented)",
                  ex.status, EXPLORATORY)
        if ok:
            res.metrics["wer"] = round(word_error_rate(fx.reference_text, body["transcription"]), 3)
        elif ex.status and ex.status >= 400:
            _contract_checks(res, ex, "stt")
        res.notes.append(note)
    return run


def voices_bad_auth(ctx: Context, res: CaseResult) -> None:
    ex = ctx.client.request(res.case_id, "GET", api.PRO_VOICES_PATH, auth="invalid", expect_auth_ok=False)
    res.exchanges.append(ex)
    res.check("HTTP 401", ex.status == 401, "401", ex.status, DOCUMENTED, D.AUTH)
    res.metrics["error_contract"] = [{"status": ex.status, "signature": signature(ex.json()),
                                      "human_message": human_message(ex.json())}]


# ============================================================================= Batch 2: streaming integrity

def _underrun(obs: api.StreamObservation, rate: int, bytes_per_sample: int) -> dict:
    times = [t for t in obs.audio_chunk_times_ms if t is not None]
    if not times:
        return {}
    t0, have, worst = times[0], 0.0, 0.0
    for t, chunk in zip(times, obs.audio_chunks):
        need = (t - t0) / 1000
        worst = max(worst, need - have)  # >0 means playback would have stalled waiting for this chunk
        have += len(chunk) / bytes_per_sample / rate
    gaps = [b - a for a, b in zip(times, times[1:])]
    return {"max_playback_stall_ms": round(max(0.0, worst) * 1000, 1), "audio_received_s": round(have, 3),
            "max_inter_chunk_gap_ms": round(max(gaps), 1) if gaps else 0.0,
            "median_inter_chunk_gap_ms": round(statistics.median(gaps), 1) if gaps else 0.0,
            "realtime_factor": round(have / ((times[-1] - t0) / 1000), 2) if times[-1] > t0 else None}


def _first_voiced_ms(obs: api.StreamObservation, rate: int) -> float | None:
    for t, chunk in zip(obs.audio_chunk_times_ms, obs.audio_chunks):
        a = analyze_pcm16(chunk, rate)
        if a.get("samples") and not a.get("all_silent"):
            return round((t or 0) + (a["leading_silence_ms"] or 0), 1)
    return None


def stream_integrity_pcm(ctx: Context, res: CaseResult) -> None:
    from .cases import _sse_checks

    ex, obs = api.stream_sse(ctx.client, res.case_id, api.tts_body(T_250, output_format="pcm"))
    res.exchanges.append(ex)
    _sse_checks(res, ex, obs)
    odd = [i for i, c in enumerate(obs.audio_chunks) if len(c) % 2]
    res.check("every PCM chunk is 16-bit sample aligned", not odd, "0 odd-length chunks", f"{len(odd)} odd",
              QUALITY)
    under = _underrun(obs, 24000, 2)
    res.metrics.update({"underrun": under, "time_to_first_voiced_audio_ms": _first_voiced_ms(obs, 24000)})
    res.check("real-time playback would not stall (this network path)", under.get("max_playback_stall_ms", 1) == 0,
              "0 ms stall", under.get("max_playback_stall_ms"), EXPLORATORY)
    if obs.audio:
        ctx.state["str_pcm_duration_s"] = len(obs.audio) / 2 / 24000
        ctx.save_private(f"{res.case_id}.wav", pcm16_to_wav(obs.audio, 24000))
        res.metrics["pcm_analysis"] = analyze_pcm16(obs.audio, 24000)


def stream_mp3(ctx: Context, res: CaseResult) -> None:
    from .cases import _sse_checks

    ex, obs = api.stream_sse(ctx.client, res.case_id, api.tts_body(T_140, output_format="mp3"))
    res.exchanges.append(ex)
    _sse_checks(res, ex, obs)
    if obs.audio_chunks:
        res.check("first chunk is MPEG audio", looks_like_mp3(obs.audio_chunks[0]), "ID3/frame sync",
                  obs.audio_chunks[0][:4].hex(), DOCUMENTED, D.CHANGELOG_2026_11_05)
        starts = sum(1 for c in obs.audio_chunks if looks_like_mp3(c))
        res.metrics.update({"chunks_starting_on_frame_sync": starts, "chunks": len(obs.audio_chunks)})
        res.check("each chunk starts on an MP3 frame boundary", starts == len(obs.audio_chunks),
                  f"{len(obs.audio_chunks)}", starts, EXPLORATORY)
        ctx.save_private(f"{res.case_id}.mp3", obs.audio)


def stream_ulaw(ctx: Context, res: CaseResult) -> None:
    from .cases import _sse_checks

    ex, obs = api.stream_sse(ctx.client, res.case_id, api.tts_body(T_140, output_format="ulaw", sample_rate=8000))
    res.exchanges.append(ex)
    _sse_checks(res, ex, obs)
    raw = obs.audio
    res.metrics["first_bytes_hex"] = raw[:4].hex()
    res.check("no RIFF header on ulaw stream (raw 8-bit samples)", raw[:4] != b"RIFF", "raw samples",
              raw[:4].hex(), DOCUMENTED, D.CHANGELOG_2026_11_05)
    if raw:
        pcm = mulaw_to_pcm16(raw)
        a = analyze_pcm16(pcm, 8000)
        cps = len(T_140) / a["duration_s"] if a.get("duration_s") else None
        res.metrics.update({"decoded": a, "chars_per_s": cps and round(cps, 2)})
        res.check("mu-law decodes to non-silent speech-rate audio", not a.get("all_silent") and cps is not None
                  and 5 <= cps <= 30, "non-silent, 5-30 chars/s", f"silent={a.get('all_silent')}, cps={cps}",
                  QUALITY)
        ctx.save_private(f"{res.case_id}.wav", pcm16_to_wav(pcm, 8000))


def stream_parity(ctx: Context, res: CaseResult) -> None:
    ex = api.synthesize(ctx.client, res.case_id, api.tts_body(T_250, output_format="pcm"))
    res.exchanges.append(ex)
    res.check("HTTP 200", ex.status == 200, "200", ex.status, DOCUMENTED, D.TTS_SYNC)
    sync_s = len(ex.body) / 2 / 24000 if ex.status == 200 else None
    sse_s = ctx.state.get("str_pcm_duration_s")
    res.metrics.update({"sync_pcm_duration_s": sync_s and round(sync_s, 3), "sse_pcm_duration_s": sse_s and
                        round(sse_s, 3), "content_type": ex.content_type})
    if sync_s and sse_s:
        ratio = sse_s / sync_s
        res.metrics["ratio_sse_over_sync"] = round(ratio, 3)
        res.check("SSE and sync durations within 20% for identical text", 0.8 <= ratio <= 1.25, "0.8-1.25",
                  round(ratio, 3), EXPLORATORY)
        ctx.save_private(f"{res.case_id}.wav", pcm16_to_wav(ex.body, 24000))


def cancellation(ctx: Context, res: CaseResult) -> None:
    ex, obs = api.stream_sse(ctx.client, res.case_id, api.tts_body(T_1000, output_format="pcm"),
                             stop_after_audio_chunks=2)
    res.exchanges.append(ex)
    res.metrics["cancelled_stream"] = {"status": ex.status, "cancelled_by_client": ex.cancelled_by_client,
                                       "audio_chunks_read": len(obs.audio_chunks), "duration_ms": ex.duration_ms
                                       and round(ex.duration_ms, 1), "done_seen": obs.done_ms is not None}
    res.check("client cancelled mid-stream cleanly (no client error)", ex.cancelled_by_client and ex.error is None,
              "cancelled, no exception", ex.error or ex.cancelled_by_client, QUALITY)
    probes = []
    for i, delay in enumerate((0.3, 3.0)):
        p = ctx.client.request(res.case_id, "POST", api.TTS_PATH, json_body=api.tts_body(T_20),
                               headers={"Content-Type": "application/json"}, delay_s=delay)
        res.exchanges.append(p)
        probes.append({"probe": i + 1, "delay_after_previous_s": delay, "status": p.status,
                       "duration_ms": p.duration_ms and round(p.duration_ms, 1)})
        if p.status != 429:
            break
    res.metrics["follow_up_probes"] = probes
    first = probes[0]["status"]
    res.check("next request after cancellation is served (slot released)", first == 200, "200",
              first, EXPLORATORY, D.CONCURRENCY)
    res.notes.append("Docs: the slot is freed 'once the request completes and returns a response'; behaviour on "
                     "client disconnect is not documented. Billing of the cancelled stream is not documented.")


def stream_long(ctx: Context, res: CaseResult) -> None:
    from .cases import _sse_checks

    ex, obs = api.stream_sse(ctx.client, res.case_id, api.tts_body(T_1000, output_format="pcm"))
    res.exchanges.append(ex)
    _sse_checks(res, ex, obs)
    if obs.audio:
        a = analyze_pcm16(obs.audio, 24000)
        cps = len(T_1000) / a["duration_s"] if a.get("duration_s") else None
        res.metrics.update({"pcm_analysis": a, "chars_per_s": cps and round(cps, 2),
                            "underrun": _underrun(obs, 24000, 2)})
        res.check("long stream: speaking rate plausible (5-30 chars/s)", cps is not None and 5 <= cps <= 30,
                  "5-30", cps, QUALITY)
        ctx.save_private(f"{res.case_id}.wav", pcm16_to_wav(obs.audio, 24000))
        ctx.listening.append({"clip": f"{res.case_id}.wav", "case_id": res.case_id, "text": T_1000,
                              "focus": "complete through the final sentence (purple elephant named Gopal)"})


def ws_word_timestamps(ctx: Context, res: CaseResult) -> None:
    from .ws import run_ws_tts

    msg = {"text": T_140, "voice_id": "meher", "model": "lightning_v3.1_pro", "sample_rate": 24000,
           "word_timestamps": True}
    # Observation window; the reproduction run uses 75 s to cover the documented 60 s idle timeout.
    deadline = float(__import__("os").environ.get("SMALLEST_QA_WS_DEADLINE_S", "30"))
    res.metrics["client_observation_window_s"] = deadline
    ex, obs = run_ws_tts(ctx.client, res.case_id, msg, overall_timeout_s=deadline)
    res.exchanges.append(ex)
    statuses = [f.get("status") for f in obs.frames]
    after_complete = [f for f, t in zip(obs.frames, obs.frame_times_ms)
                      if obs.complete_ms is not None and t > obs.complete_ms]
    res.metrics["frames_after_complete"] = after_complete[:5]
    chunk_times = [t for f, t in zip(obs.frames, obs.frame_times_ms) if f.get("status") == "chunk"]
    res.metrics["last_chunk_ms"] = chunk_times[-1] if chunk_times else None
    if chunk_times and obs.complete_ms:  # docs: complete_backoff_ms default 4000 ms
        res.metrics["complete_after_last_chunk_ms"] = round(obs.complete_ms - chunk_times[-1], 1)
    res.metrics["closed_after_complete_ms"] = (round(obs.closed_ms - obs.complete_ms, 1)
                                               if obs.closed_by_server and obs.complete_ms else None)
    res.metrics.update({"frame_status_counts": {s: statuses.count(s) for s in set(statuses)},
                        "close_code": obs.close_code, "closed_by_server": obs.closed_by_server,
                        "timed_out": obs.timed_out, "word_events": obs.word_events[:40],
                        "handshake_ms": obs.handshake_ms and round(obs.handshake_ms, 1),
                        "first_audio_frame_ms": obs.first_audio_ms and round(obs.first_audio_ms, 1),
                        "complete_ms": obs.complete_ms and round(obs.complete_ms, 1)})
    res.check("WebSocket handshake succeeded", ex.status == 101, "101", ex.status, DOCUMENTED, D_WS)
    res.check(">= 1 `chunk` frame with audio", statuses.count("chunk") >= 1 and bool(obs.audio_chunks), ">= 1",
              statuses.count("chunk"), DOCUMENTED, D.TTS_STREAMING)
    res.check("exactly one `complete` frame", statuses.count("complete") == 1, 1, statuses.count("complete"),
              DOCUMENTED, D.TTS_STREAMING)
    gap = res.metrics["closed_after_complete_ms"]
    # Docs: "`complete` - terminal frame; the server closes the WebSocket after this." The 5 s bound is our
    # operationalisation of "after this"; the documented idle timeout (60 s) is a different mechanism.
    res.check("server closes the socket promptly after `complete` (<= 5 s)",
              obs.closed_by_server and gap is not None and gap <= 5000, "server close within 5 s of complete",
              f"closed_by_server={obs.closed_by_server} after={gap} ms timed_out={obs.timed_out}", DOCUMENTED,
              D.TTS_STREAMING)
    res.check("no error frame after a successful `complete`",
              not any(f.get("status") == "error" for f in after_complete), "none",
              [f.get("message") for f in after_complete if f.get("status") == "error"] or "none", QUALITY)
    res.check("all frames are valid JSON", obs.invalid_frames == 0, 0, obs.invalid_frames, DOCUMENTED,
              D.TTS_STREAMING)
    words = obs.word_events
    res.check("word_timestamp events emitted for `meher` (WS reference lists meher)", len(words) > 0, "> 0",
              len(words), DOCUMENTED, D_WS)
    if words:
        mono = all((a.get("start") or 0) <= (b.get("start") or 0) for a, b in zip(words, words[1:]))
        spans = all((w.get("start") or 0) <= (w.get("end") or 0) for w in words)
        recall = key_token_hits(" ".join(str(w.get("word")) for w in words), [[t] for t in normalize(T_140)])
        res.check("word timestamps monotonic with start <= end", mono and spans, True, f"{mono}/{spans}", QUALITY)
        res.metrics["word_recall_vs_text"] = recall
    if obs.audio:
        ctx.save_private(f"{res.case_id}.wav", pcm16_to_wav(obs.audio, 24000))


def ws_bad_voice(ctx: Context, res: CaseResult) -> None:
    from .ws import run_ws_tts

    msg = {"text": SHORT_EN, "voice_id": "qa_nonexistent_voice_zz9", "model": "lightning_v3.1_pro",
           "sample_rate": 24000}
    ex, obs = run_ws_tts(ctx.client, res.case_id, msg, overall_timeout_s=15)
    res.exchanges.append(ex)
    err = [f for f in obs.frames if f.get("status") == "error"]
    res.metrics.update({"frames": obs.frames[:5], "close_code": obs.close_code, "timed_out": obs.timed_out,
                        "error_frame_signature": signature(err[0]) if err else None})
    res.check("invalid voice produces an error frame (no audio)", bool(err) and not obs.audio_chunks,
              "status=error frame", f"{len(err)} error frames, {len(obs.audio_chunks)} audio",
              EXPLORATORY, D.TTS_STREAMING)
    res.check("connection does not hang until the client deadline", not obs.timed_out, "server closes/answers",
              f"timed_out={obs.timed_out}", QUALITY)


# ============================================================================= Batch 3: STT accuracy

def _stt_fixture(fixture_id: str, model: str = "pulse", wer_max: float | None = 0.25, *,
                 params: dict[str, str] | None = None, extra: Callable | None = None,
                 expect_empty: bool = False, tokens: list[list[str]] | None = None, use_cer: bool = False
                 ) -> Callable[[Context, CaseResult], None]:
    def run(ctx: Context, res: CaseResult) -> None:
        fx = ctx.p2_fixtures.get(fixture_id)
        if fx is None or isinstance(fx, str):
            res.notes.append(f"fixture {fixture_id} unavailable: {fx}")
            res.classification = NOT_TESTED
            return
        res.metrics["fixture"] = fx.describe()
        ex, body = _transcribe(ctx, res.case_id, fx.data, fx.recipe.language, model, **(params or {}))
        res.exchanges.append(ex)
        if expect_empty:
            # Silence: behaviour for an explicit language is not documented.
            tx = (body or {}).get("transcription") if body else None
            res.metrics.update({"status": ex.status, "transcription": tx, "signature": signature(ex.json())})
            res.check("silence handled without a 5xx", ex.status is not None and ex.status < 500, "< 500", ex.status,
                      QUALITY)
            res.check("no hallucinated words on non-speech input",
                      ex.status != 200 or not (isinstance(tx, str) and normalize(tx)), "empty transcription",
                      repr(tx), QUALITY)
            return
        res.check("HTTP 200", ex.status == 200, "200", ex.status, DOCUMENTED, D.STT_TRANSCRIBE)
        tx = (body or {}).get("transcription")
        if not isinstance(tx, str):
            return
        ref = fx.recipe.reference
        wer, cer = word_error_rate(ref, tx), char_error_rate(ref, tx)
        res.metrics["words"] = (body or {}).get("words", [])[:300]  # synthetic audio only; full timestamps
        res.metrics.update({"transcription": tx, "reference": ref, "wer": round(wer, 3), "cer": round(cer, 3),
                            "audio_s": round(fx.duration_s, 2), "latency_ms": ex.duration_ms and round(ex.duration_ms)})
        if wer_max is not None:
            metric, val = ("CER", cer) if use_cer else ("WER", wer)
            res.check(f"{metric} <= {wer_max} on clean synthetic speech", val <= wer_max, f"<= {wer_max}",
                      round(val, 3), QUALITY)
        if tokens:
            hits = key_token_hits(tx, tokens)
            res.metrics["key_tokens"] = hits
            res.check("expected tokens present", hits["hit"] == hits["total"], hits["total"], hits, EXPLORATORY)
        if extra:
            extra(ctx, res, fx, body)
    return run


def _diar_checks(ctx: Context, res: CaseResult, fx, body: dict) -> None:
    words = body.get("words") or []
    res.check("diarize=true: every word carries `speaker`", bool(words) and all("speaker" in w for w in words),
              "speaker on all words", f"{sum(1 for w in words if 'speaker' in w)}/{len(words)}", DOCUMENTED,
              D.STT_TRANSCRIBE)
    speakers = sorted({w.get("speaker") for w in words if "speaker" in w}, key=str)
    res.metrics["speakers"] = speakers
    res.check("two synthetic speakers separated", len(speakers) == fx.recipe.expected_speakers,
              fx.recipe.expected_speakers, len(speakers), EXPLORATORY)


def _gap_checks(ctx: Context, res: CaseResult, fx, body: dict) -> None:
    words = body.get("words") or []
    res.check("words[] present with word_timestamps=true", bool(words), "non-empty", len(words), DOCUMENTED,
              D.STT_TRANSCRIBE)
    if len(words) < 2:
        return
    gaps = [(words[i + 1]["start"] - words[i]["end"], i) for i in range(len(words) - 1)]
    g, i = max(gaps)
    s1, s2 = [s for s in fx.segments if s["kind"] == "say"]
    res.metrics["timestamp_gap"] = {"observed_gap_s": [words[i]["end"], words[i + 1]["start"]],
                                    "true_speech_gap_s": [s1["voiced_end_s"], s2["voiced_start_s"]]}
    ok = abs(words[i]["end"] - s1["voiced_end_s"]) <= 0.3 and abs(words[i + 1]["start"] - s2["voiced_start_s"]) <= 0.3
    res.check("largest word gap aligns with the inserted silence (+/-0.3 s)", ok, "both edges within 0.3 s",
              res.metrics["timestamp_gap"], QUALITY)


# ============================================================================= Batch 4/5: TTS correctness

def _tts_case(text: str, *, language: str = "en", groups: list[list[str]] | None = None, absent: list[str] = (),
              roundtrip: bool = True, focus: str = "", use_cer_ref: bool = False, numeric: bool = False,
              **params: Any) -> Callable[[Context, CaseResult], None]:
    def run(ctx: Context, res: CaseResult) -> None:
        ex = api.synthesize(ctx.client, res.case_id, api.tts_body(text, language=language, **params))
        res.exchanges.append(ex)
        res.metrics["params"] = {"language": language, **params}
        pcm = _tts_integrity(ctx, res, ex, text, listen_focus=focus)
        if pcm is None or not roundtrip:
            return
        _roundtrip(ctx, res, ex.body, text, language, groups or [], absent, numeric=numeric)
        if use_cer_ref and "roundtrip" in res.metrics:
            res.metrics["roundtrip"]["cer_vs_input_text"] = round(
                char_error_rate(text, res.metrics["roundtrip"]["transcription"]), 3)
    return run


def param_speed(speed: float) -> Callable[[Context, CaseResult], None]:
    def run(ctx: Context, res: CaseResult) -> None:
        ex = api.synthesize(ctx.client, res.case_id, api.tts_body(T_140, speed=speed))
        res.exchanges.append(ex)
        pcm = _tts_integrity(ctx, res, ex, T_140, label=f"speed{speed}")
        if pcm is not None:
            dur = len(pcm) / 2 / 24000
            ctx.state.setdefault("speed_durations", {})[speed] = dur
            base = ctx.state["speed_durations"].get(1.0)
            res.metrics["duration_s"] = round(dur, 3)
            if base and speed != 1.0:
                ratio = base / dur
                res.metrics["speedup_vs_1x"] = round(ratio, 2)
                lo, hi = speed * 0.6, speed * 1.4
                res.check(f"duration scales with speed={speed} (speed-up {lo:.2f}-{hi:.2f}x)", lo <= ratio <= hi,
                          f"{lo:.2f}-{hi:.2f}", round(ratio, 2), EXPLORATORY, D.TTS_SYNC)
    return run


def param_rate(rate: int) -> Callable[[Context, CaseResult], None]:
    def run(ctx: Context, res: CaseResult) -> None:
        ex = api.synthesize(ctx.client, res.case_id, api.tts_body(T_20, sample_rate=rate))
        res.exchanges.append(ex)
        _tts_integrity(ctx, res, ex, T_20, sample_rate=rate)
    return run


# ============================================================================= Batch 6: latency

def latency(text: str, n: int, *, fresh: bool = False) -> Callable[[Context, CaseResult], None]:
    def run(ctx: Context, res: CaseResult) -> None:
        ttfb, voiced, total, rtf = [], [], [], []
        for i in range(n):
            ex, obs = api.stream_sse(ctx.client, res.case_id, api.tts_body(text, output_format="pcm"),
                                     fresh_connection=fresh)
            res.exchanges.append(ex)
            ok = ex.status == 200 and obs.done_ms is not None
            res.check(f"sample {i + 1}: 200 + completed", ok, "200 + done", ex.status, DOCUMENTED, D.TTS_STREAMING)
            if ok:
                ttfb.append(ex.ttfb_ms)
                total.append(ex.duration_ms)
                v = _first_voiced_ms(obs, 24000)
                if v is not None:
                    voiced.append(v)
                dur = len(obs.audio) / 2 / 24000
                rtf.append(dur / (ex.duration_ms / 1000))
        res.metrics.update({"chars": len(text), "fresh_connection": fresh,
                            "method": "sequential, concurrency 1, client wall clock incl. network; nearest-rank p95",
                            "ttfb_ms": summarize(ttfb), "first_voiced_audio_ms": summarize(voiced),
                            "total_ms": summarize(total), "audio_s_per_wall_s": summarize(rtf),
                            "raw_ttfb_ms": [round(v, 1) for v in ttfb], "raw_total_ms": [round(v, 1) for v in total]})
        res.notes.append(f"n={len(total)}. Docs state 'First chunk arrives in ~100ms' (streaming page) and TTFB "
                         "200 ms (model cards); client-side numbers include network RTT and cannot confirm or "
                         "refute either.")
    return run


# ============================================================================= catalogue

def _c(cid, batch, prio, area, title, req, expected, refs, n, fn, **kw) -> CaseSpec:
    return CaseSpec(cid, area, title, req, expected, tuple(refs), n, fn, phase=2, batch=batch, priority=prio, **kw)


_F2_REFS = (D.TTS_SYNC, D.CHANGELOG_2026_11_05, D.TTS_PRO_CARD, D.DEPRECATIONS)
_KEYS_N01 = [["1250", "one thousand two hundred fifty", "twelve hundred fifty", "twelve fifty"],
             ["4572", "four five seven two", "forty five seventy two", "four thousand five hundred seventy two"],
             ["3 days", "three days"]]
_KEYS_N02 = [["499", "four hundred ninety nine", "four hundred and ninety nine", "four ninety nine"],
             ["rupees", "rupee", "rs"], ["120", "one hundred twenty", "hundred and twenty", "a hundred twenty"],
             ["dollars", "dollar"], ["60", "sixty"], ["euros", "euro"]]
T_N01 = "Your balance is 1,250.75 dollars and order number 4572 will arrive in 3 days."
T_N02 = "The fare is ₹499, the hotel costs $120, and the visa fee is €60."
T_DATE = "The meeting is on 05/03/2024."
T_MATH = "What is 6 x 7? It is 42."
T_UNI = "Wait… really? “Yes” — it’s done! 🎉 Café au lait, déjà vu."
T_HI = "मेरा नाम प्रिया है और मैं दिल्ली में रहती हूँ।"
T_HINGLISH_ROMAN = "Kal ki meeting teen baje hai, please apna laptop le aana."
T_NAMES = "Sriram Venkataraman, Aishwarya Iyer and Gurpreet Singh Dhillon joined the call from Thiruvananthapuram."
T_ABBR = "Dr. Sharma lives on MG Rd. near the ATM, approx. 5 km from the IIT campus."
T_PHONE = "Please call me back on 9876543210."

P2_CASES: list[CaseSpec] = [
    # ---------------- Batch 1 (P0): F2 isolation, TTS error contract, SDK + docs examples -----------------
    _c("P2-F2-01", "1", "P0", "F2 reassessment", "Pro voice catalogue (ids recorded)", DOCUMENTED,
       "200 JSON catalogue", (D.DEPRECATIONS,), 1, f2_pro_catalogue),
    _c("P2-F2-02", "1", "P0", "F2 reassessment", "Lightning v3.1 voice catalogue (legacy route, ids recorded)",
       DOCUMENTED, "200 JSON catalogue (route retiring 2026-11-30)", (D_V31_CARD, D.DEPRECATIONS), 1,
       f2_v31_catalogue),
    _c("P2-F2-03", "1", "P0", "F2 reassessment", "v3.1-only voice on its own model (lightning_v3.1)", DOCUMENTED,
       "200 valid WAV: proves the probe voice exists and works", _F2_REFS, 1, _f2_probe("lightning_v3.1",
                                                                                         "v31_only", True),
       synth_chars=45, depends_on=("P2-F2-01", "P2-F2-02"), requires_human=True),
    _c("P2-F2-04", "1", "P0", "F2 reassessment", "Same v3.1-only voice on lightning_v3.1_pro (true mismatch)",
       DOCUMENTED, "400 mismatch per API ref + changelog; Pro card FAQ says not rejected", _F2_REFS, 1,
       _f2_probe("lightning_v3.1_pro", "v31_only", False), depends_on=("P2-F2-03",)),
    _c("P2-F2-05", "1", "P0", "F2 reassessment", "Same v3.1-only voice with model omitted", DOCUMENTED,
       "200: model is chosen from the voice when omitted", _F2_REFS, 1, _f2_probe(None, "v31_only", True),
       synth_chars=45, depends_on=("P2-F2-03",)),
    _c("P2-F2-06", "1", "P0", "F2 reassessment", "Pro-only voice on lightning_v3.1 (reverse mismatch)", DOCUMENTED,
       "400: 'a voice used with the wrong model returns 400'", _F2_REFS, 1,
       _f2_probe("lightning_v3.1", "pro_only", False), depends_on=("P2-F2-01", "P2-F2-02")),
    _c("P2-ERR-01", "1", "P0", "Error contract", "TTS: missing required voice_id", DOCUMENTED,
       "400 + documented error schema", (D.TTS_SYNC,), 1, _tts_bad(_without("voice_id"))),
    _c("P2-ERR-02", "1", "P0", "Error contract", "TTS: malformed JSON body", QUALITY,
       "4xx + error schema (status for malformed JSON not documented)", (D.TTS_SYNC,), 1,
       _tts_bad(raw=b'{"text": "hello", "voice_id": ', documented_400=False)),
    _c("P2-ERR-03", "1", "P0", "Error contract", "TTS: speed=2.5 outside documented 0.5-2 range", QUALITY,
       "4xx (range documented; enforcement not stated)", (D.TTS_SYNC,), 1,
       _tts_bad(api.tts_body(SHORT_EN, speed=2.5), documented_400=False), synth_chars=len(SHORT_EN)),
    _c("P2-ERR-04", "1", "P0", "Error contract", "TTS: sample_rate=22050 (not in enum)", DOCUMENTED,
       "400 + error schema", (D.TTS_SYNC,), 1, _tts_bad(api.tts_body(SHORT_EN, sample_rate=22050))),
    _c("P2-ERR-05", "1", "P0", "Error contract", "TTS: output_format=ogg (not in enum)", DOCUMENTED,
       "400 + error schema", (D.TTS_SYNC,), 1, _tts_bad(api.tts_body(SHORT_EN, output_format="ogg"))),
    _c("P2-ERR-06", "1", "P0", "Error contract", "TTS: language=xx (not in enum)", DOCUMENTED,
       "400 + error schema", (D.TTS_SYNC,), 1, _tts_bad(api.tts_body(SHORT_EN, language="xx"))),
    _c("P2-SDK-01", "1", "P0", "SDK", "smallestai 5.14.0 synthesize_tts (quickstart parameters)", DOCUMENTED,
       "valid 24 kHz WAV, one HTTP attempt", (D_TTS_QS,), 1, sdk_tts, synth_chars=42),
    _c("P2-SDK-02", "1", "P0", "SDK", "smallestai 5.14.0 synthesize_sse_tts yields audio", DOCUMENTED,
       "SDK yields the streamed audio (offline replay predicts 0 items: candidate)", (D_TTS_QS, D.TTS_STREAMING),
       1, sdk_sse, synth_chars=len(SHORT_EN)),
    _c("P2-SDK-03", "1", "P0", "SDK", "smallestai 5.14.0 speech_to_text.transcribe", DOCUMENTED,
       "typed TranscriptionResponse with transcription", (D.STT_TRANSCRIBE,), 1, sdk_stt, stt_audio_seconds=6.3),
    _c("P2-DOC-01", "1", "P1", "Docs examples", "TTS quickstart (requests) run verbatim", DOCUMENTED,
       "exit 0 and output.wav is real audio", (D_TTS_QS,), 1, _doc_example("tts_quickstart_requests.py", 42),
       synth_chars=42),
    _c("P2-DOC-02", "1", "P1", "Docs examples", "STT quickstart (requests, pulse-pro, GitHub sample) verbatim",
       DOCUMENTED, "exit 0, prints transcription", (D.STT_QUICKSTART,), 1,
       _doc_example("stt_quickstart_requests.py", 0, 10.0), stt_audio_seconds=10.0),
    _c("P2-DOC-03", "1", "P1", "Docs examples", "Cookbook transcribe-python.py (audio by URL, pulse) verbatim",
       DOCUMENTED, "exit 0, prints transcription (URL ingestion path)", (D_COOKBOOK, D.STT_TRANSCRIBE), 1,
       _doc_example("cookbook_transcribe_python.py", 0, 10.0), stt_audio_seconds=10.0),
    # ---------------- Batch 2 (P0/P1): cross-endpoint errors, streaming integrity, WS, cancellation -------
    _c("P2-ERR-10", "2", "P0", "Error contract", "SSE: unknown voice", QUALITY,
       "4xx before streaming; error shape consistent with sync TTS (no SSE error schema documented)",
       (D.TTS_STREAMING, D.TTS_SYNC), 1, sse_bad_voice),
    _c("P2-ERR-11", "2", "P0", "Error contract", "SSE: missing Authorization", DOCUMENTED, "401",
       (D.AUTH,), 1, sse_no_auth),
    _c("P2-ERR-12", "2", "P1", "Error contract", "SSE: empty text", EXPLORATORY, "4xx (not documented for SSE)",
       (D.TTS_STREAMING,), 1, sse_empty_text),
    _c("P2-ERR-13", "2", "P0", "Error contract", "STT: pulse-pro with language=hi", DOCUMENTED,
       "400 ('only en is accepted; any other value returns HTTP 400') + STT schema", (D.STT_TRANSCRIBE,), 1,
       _stt_bad({"model": "pulse-pro", "language": "hi"}), stt_audio_seconds=6.3),
    _c("P2-ERR-14", "2", "P0", "Error contract", "STT: undecodable audio bytes", QUALITY,
       "4xx with documented code AudioDecodeError (status not documented)", (D.STT_TRANSCRIBE,), 1,
       _stt_bad({"model": "pulse", "language": "en"}, audio="corrupt", documented_400=False,
                code_expected="AudioDecodeError"), stt_audio_seconds=1.0),
    _c("P2-ERR-15", "2", "P0", "Error contract", "STT: invalid API key", DOCUMENTED,
       "401 + STT schema (`error` string for auth errors)", (D.STT_TRANSCRIBE, D.AUTH), 1,
       _stt_bad({"model": "pulse", "language": "en"}, auth="invalid", expect_status=401)),
    _c("P2-ERR-16", "2", "P1", "Error contract", "STT: Content-Type audio/wav (used in a docs example)",
       EXPLORATORY, "spec lists only application/octet-stream; language-detection page uses audio/wav",
       (D.STT_TRANSCRIBE, D_LANGDET), 1, stt_probe_ok({"model": "pulse", "language": "en"}, "audio/wav",
                                                      "Probes a documentation inconsistency."), stt_audio_seconds=6.3),
    _c("P2-ERR-17", "2", "P1", "Error contract", "get_voices: invalid API key", DOCUMENTED, "401",
       (D.AUTH,), 1, voices_bad_auth),
    _c("P2-ERR-18", "2", "P1", "Error contract", "STT: language omitted", EXPLORATORY,
       "'optional' but 'Always pass language'; default not stated", (D.STT_TRANSCRIBE,), 1,
       stt_probe_ok({"model": "pulse"}, "application/octet-stream", "Default language is not documented."),
       stt_audio_seconds=6.3),
    _c("P2-STR-01", "2", "P0", "Streaming", "SSE pcm 250 chars: chunk alignment, gaps, playback stall analysis",
       DOCUMENTED, "documented framing; 16-bit aligned chunks; no playback stall", (D.TTS_STREAMING,), 1,
       stream_integrity_pcm, synth_chars=len(T_250)),
    _c("P2-STR-02", "2", "P1", "Streaming", "SSE mp3 framing", DOCUMENTED, "MPEG frames ('mp3 streams MP3 frames')",
       (D.TTS_STREAMING, D.CHANGELOG_2026_11_05), 1, stream_mp3, synth_chars=len(T_140)),
    _c("P2-STR-03", "2", "P1", "Streaming", "SSE ulaw 8 kHz", DOCUMENTED, "raw 8-bit samples, decodable",
       (D.CHANGELOG_2026_11_05,), 1, stream_ulaw, synth_chars=len(T_140)),
    _c("P2-STR-04", "2", "P1", "Streaming", "Sync vs SSE duration parity (same 250-char text)", EXPLORATORY,
       "durations within 20%", (D.TTS_SYNC, D.TTS_STREAMING), 1, stream_parity, synth_chars=len(T_250),
       depends_on=("P2-STR-01",)),
    _c("P2-STR-08", "2", "P1", "Streaming", "SSE 1000-char stream completes", DOCUMENTED,
       "single terminal frame; full-length audio", (D.TTS_STREAMING,), 1, stream_long, synth_chars=len(T_1000),
       requires_human=True),
    _c("P2-WS-01", "2", "P0", "Streaming", "WebSocket TTS with word_timestamps (meher)", DOCUMENTED,
       "chunk frames, one complete, server close; word events for meher (docs conflict on meher)",
       (D_WS, D.TTS_STREAMING, D_V31_CARD), 1, ws_word_timestamps, synth_chars=len(T_140)),
    _c("P2-WS-02", "2", "P1", "Streaming", "WebSocket unknown voice", EXPLORATORY,
       "error frame, no audio, no hang (error frame schema not documented)", (D_WS,), 1, ws_bad_voice),
    _c("P2-STR-05", "2", "P0", "Streaming", "Client cancellation then immediate follow-up request", EXPLORATORY,
       "clean cancel; observe whether the concurrency slot is released (up to 2 follow-up probes)",
       (D.CONCURRENCY, D.TTS_STREAMING), 3, cancellation, synth_chars=len(T_1000) + 2 * len(T_20), max_requests=3),
    # ---------------- Batch 3 (P1): STT accuracy ------------------------------------------------------------
    *[_c(f"P2-STT-{i:02d}", "3", "P1", "STT accuracy", title, QUALITY, exp, refs, 1, fn, stt_audio_seconds=6.0,
         p2_fixtures=(fx,))
      for i, (fx, title, exp, refs, fn) in enumerate([
          ("acc_en_in_rishi", "Indian English synthetic voice (Rishi), pulse", "WER <= 0.25",
           (D.STT_PULSE_CARD,), _stt_fixture("acc_en_in_rishi")),
          ("acc_en_in_rishi", "Indian English synthetic voice (Rishi), pulse-pro", "WER <= 0.25",
           (D_PULSE_PRO_CARD,), _stt_fixture("acc_en_in_rishi", "pulse-pro")),
          ("acc_en_gb_daniel", "British English synthetic voice (Daniel)", "WER <= 0.25", (D.STT_PULSE_CARD,),
           _stt_fixture("acc_en_gb_daniel")),
          ("acc_en_au_karen", "Australian English synthetic voice (Karen)", "WER <= 0.25", (D.STT_PULSE_CARD,),
           _stt_fixture("acc_en_au_karen")),
          ("noise_snr10", "White noise, 10 dB SNR", "WER reported (no threshold)", (D.STT_PULSE_CARD,),
           _stt_fixture("noise_snr10", wer_max=None)),
          ("noise_snr0", "White noise, 0 dB SNR", "WER reported (no threshold)", (D.STT_PULSE_CARD,),
           _stt_fixture("noise_snr0", wer_max=None)),
          ("short_yes", "Single-word utterance 'Yes.'", "exact match", (D.STT_TRANSCRIBE,),
           _stt_fixture("short_yes", wer_max=0.0)),
          ("short_no_thanks", "Two-word utterance 'No, thanks.' (Rishi)", "exact match", (D.STT_TRANSCRIBE,),
           _stt_fixture("short_no_thanks", wer_max=0.0)),
          ("silence_digital", "3 s digital silence", "no 5xx; no hallucinated words (undocumented behaviour)",
           (D.STT_TRANSCRIBE,), _stt_fixture("silence_digital", expect_empty=True)),
          ("silence_noise_floor", "3 s low-level noise, no speech", "no hallucinated words", (D.STT_TRANSCRIBE,),
           _stt_fixture("silence_noise_floor", expect_empty=True)),
          ("hi_lekha", "Hindi (Devanagari) synthetic voice, language=hi", "CER <= 0.25", (D.STT_PULSE_CARD,),
           _stt_fixture("hi_lekha", use_cer=True)),
          ("hinglish_smallest_tts", "Hindi-English code-switched (Smallest TTS output), language=hi",
           "English words kept in Roman script ('hi also keeps English words in Roman script')",
           (D.STT_PULSE_CARD, D_LANGDET), _stt_fixture("hinglish_smallest_tts", wer_max=None,
                                                       tokens=[["booking"], ["confirm"], ["call"], ["slot"]])),
          ("tel_8k", "8 kHz telephony-band audio (16 kHz recommended)", "WER reported", (D.STT_PULSE_CARD,),
           _stt_fixture("tel_8k", wer_max=None)),
          ("diarize_2spk", "Two speakers with diarize=true", "speaker on every word; 2 speakers",
           (D.STT_TRANSCRIBE,), _stt_fixture("diarize_2spk", wer_max=None,
                                             params={"diarize": "true", "word_timestamps": "true"},
                                             extra=_diar_checks)),
          ("gap_1500ms", "Word timestamps vs a known 1.5 s inserted pause", "gap edges within 0.3 s",
           (D.STT_TRANSCRIBE,), _stt_fixture("gap_1500ms", wer_max=None, params={"word_timestamps": "true"},
                                             extra=_gap_checks)),
      ], start=1)],
    # ---------------- Batch 4 (P1): TTS normalisation round trips + params ------------------------------
    _c("P2-TTS-N01", "4", "P1", "TTS correctness", "Numbers: decimals, order id, count", EXPLORATORY,
       "integrity + round-trip recovers amounts", (D.TTS_SYNC,), 2, _tts_case(T_N01, groups=_KEYS_N01,
                                                                              focus="number reading", numeric=True),
       synth_chars=len(T_N01), stt_audio_seconds=6, requires_human=True),
    _c("P2-TTS-N02", "4", "P1", "TTS correctness", "Currency: ₹, $, €", EXPLORATORY,
       "integrity + round-trip recovers amounts and currency names", (D.TTS_SYNC,), 2,
       _tts_case(T_N02, groups=_KEYS_N02, focus="currency symbols read as rupees/dollars/euros", numeric=True),
       synth_chars=len(T_N02), stt_audio_seconds=6, requires_human=True),
    _c("P2-TTS-N03", "4", "P1", "TTS correctness", "Date 05/03/2024 with date_format=US", DOCUMENTED,
       "'May third, twenty twenty four' (documented example)", (D_BEST, D.TTS_SYNC), 2,
       _tts_case(T_DATE, date_format="US", groups=[["may"], ["third", "3rd", "3"]], absent=["march"],
                 focus="date read as May 3"), synth_chars=len(T_DATE), stt_audio_seconds=4, requires_human=True),
    _c("P2-TTS-N04", "4", "P1", "TTS correctness", "Date 05/03/2024 with date_format=EU", DOCUMENTED,
       "'fifth March, twenty twenty four' (documented example)", (D_BEST, D.TTS_SYNC), 2,
       _tts_case(T_DATE, date_format="EU", groups=[["march"], ["fifth", "5th", "5"]], absent=["may"],
                 focus="date read as 5 March"), synth_chars=len(T_DATE), stt_audio_seconds=4, requires_human=True),
    _c("P2-TTS-N05", "4", "P1", "TTS correctness", "math_notation=true: '6 x 7'", DOCUMENTED,
       "'six times seven' (documented example)", (D_MATH,), 2,
       _tts_case(T_MATH, math_notation=True, groups=[["times", "into", "multiplied"]], focus="'x' read as times",
                 numeric=True),
       synth_chars=len(T_MATH), stt_audio_seconds=4, requires_human=True),
    _c("P2-TTS-N06", "4", "P1", "TTS correctness", "Unicode punctuation, emoji, accented Latin", EXPLORATORY,
       "200 + integrity; emoji not voiced", (D.TTS_SYNC,), 2,
       _tts_case(T_UNI, groups=[["cafe", "café"], ["deja", "déjà"]], absent=["party", "popper", "emoji"],
                 focus="punctuation pauses; emoji silent; café/déjà vu"),
       synth_chars=len(T_UNI), stt_audio_seconds=5, requires_human=True),
    _c("P2-PAR-00", "4", "P2", "TTS params", "speed=1.0 baseline (140 chars)", DOCUMENTED, "valid WAV",
       (D.TTS_SYNC,), 1, param_speed(1.0), synth_chars=len(T_140)),
    _c("P2-PAR-01", "4", "P2", "TTS params", "speed=0.5", DOCUMENTED, "valid WAV, ~2x longer", (D.TTS_SYNC,), 1,
       param_speed(0.5), synth_chars=len(T_140), depends_on=("P2-PAR-00",)),
    _c("P2-PAR-02", "4", "P2", "TTS params", "speed=2.0", DOCUMENTED, "valid WAV, ~2x shorter", (D.TTS_SYNC,), 1,
       param_speed(2.0), synth_chars=len(T_140), depends_on=("P2-PAR-00",)),
    _c("P2-PAR-03", "4", "P2", "TTS params", "sample_rate=8000 WAV header", DOCUMENTED, "8 kHz WAV",
       (D.TTS_SYNC,), 1, param_rate(8000), synth_chars=len(T_20)),
    # ---------------- Batch 5 (P1): languages, names, length ---------------------------------------------
    _c("P2-TTS-N07", "5", "P1", "TTS correctness", "Hindi Devanagari, language=hi", EXPLORATORY,
       "integrity + round-trip CER", (D.TTS_PRO_CARD,), 2, _tts_case(T_HI, language="hi", groups=[],
                                                                       use_cer_ref=True, focus="Hindi pronunciation"),
       synth_chars=len(T_HI), stt_audio_seconds=5, requires_human=True),
    _c("P2-TTS-N08", "5", "P1", "TTS correctness", "Romanised Hinglish, language=hi", EXPLORATORY,
       "integrity + English words recovered", (D.TTS_PRO_CARD,), 2,
       _tts_case(T_HINGLISH_ROMAN, language="hi", groups=[["meeting"], ["please"], ["laptop"]],
                 focus="romanised Hindi read naturally"), synth_chars=len(T_HINGLISH_ROMAN), stt_audio_seconds=5,
       requires_human=True),
    _c("P2-TTS-N09", "5", "P1", "TTS correctness", "Indian names and place names", EXPLORATORY,
       "integrity only; pronunciation needs listening", (D.TTS_SYNC,), 1,
       _tts_case(T_NAMES, roundtrip=False, focus="name pronunciation"), synth_chars=len(T_NAMES),
       requires_human=True),
    _c("P2-TTS-N10", "5", "P1", "TTS correctness", "Abbreviations (Dr., Rd., ATM, approx., km, IIT)", EXPLORATORY,
       "integrity only; expansion needs listening", (D.TTS_SYNC,), 1,
       _tts_case(T_ABBR, roundtrip=False, focus="abbreviation expansion"), synth_chars=len(T_ABBR),
       requires_human=True),
    _c("P2-TTS-N11", "5", "P1", "TTS correctness", "Phone number 9876543210", DOCUMENTED,
       "documented 3-4-3 grouping ('987-6543-210'); grouping needs listening", (D_BEST,), 1,
       _tts_case(T_PHONE, roundtrip=False, focus="3-4-3 digit grouping"), synth_chars=len(T_PHONE),
       requires_human=True),
    _c("P2-TTS-L01", "5", "P1", "TTS correctness", "1000-character paragraph (sync)", DOCUMENTED,
       "valid WAV; completion verified by round-trip of the final sentence", (D.TTS_SYNC, D_BEST), 2,
       _tts_case(T_1000, groups=[["purple"], ["elephant"], ["gopal", "gopaal"]],
                 focus="no truncation; consistent voice"), synth_chars=len(T_1000), stt_audio_seconds=70,
       requires_human=True),
    # ---------------- Batch 6 (P2): latency ---------------------------------------------------------------
    _c("P2-LAT-01", "6", "P2", "Latency", "SSE TTFB, 19-char text, n=3", EXPLORATORY, "measurement only",
       (D.TTS_STREAMING,), 3, latency(T_20, 3), synth_chars=3 * len(T_20)),
    _c("P2-LAT-02", "6", "P2", "Latency", "SSE TTFB, ~110-char text, n=5", EXPLORATORY, "measurement only",
       (D.TTS_STREAMING,), 5, latency(T_140, 5), synth_chars=5 * len(T_140)),
    _c("P2-LAT-03", "6", "P2", "Latency", "SSE TTFB, ~500-char text, n=3", EXPLORATORY, "measurement only",
       (D.TTS_STREAMING,), 3, latency(T_500, 3), synth_chars=3 * len(T_500)),
    _c("P2-LAT-04", "6", "P2", "Latency", "SSE TTFB on a fresh TCP/TLS connection, n=2", EXPLORATORY,
       "measurement only (cold vs warm)", (D.TTS_STREAMING,), 2, latency(T_140, 2, fresh=True),
       synth_chars=2 * len(T_140)),
]

P2_BY_ID = {c.case_id: c for c in P2_CASES}
BATCHES = sorted({c.batch for c in P2_CASES})


def batch_cases(batch: str) -> list[CaseSpec]:
    return [c for c in P2_CASES if c.batch == batch]


def planned(spec: CaseSpec) -> int:
    return spec.max_requests or spec.planned_requests


# ============================================================================= Batch 3h: real-human STT (optional variant)

def _human_case(prompt_id: str) -> Callable[[Context, CaseResult], None]:
    def run(ctx: Context, res: CaseResult) -> None:
        from .human import PROMPTS_BY_ID, load_approved_audio, load_clip

        p = PROMPTS_BY_ID[prompt_id]
        root = ctx.state.get("human_dir")
        got = load_approved_audio(prompt_id, root) if root else load_approved_audio(prompt_id)
        if got is None:
            m = load_clip(prompt_id, root) if root else load_clip(prompt_id)
            res.notes.append("Not sent: " + ("no recording" if not m else
                                             "approval missing or stale (clip changed after approval)"))
            res.classification = NOT_TESTED
            return  # zero requests: unapproved audio never leaves the machine
        wav, meta = got
        share = bool(meta.get("share_transcript_in_evidence"))
        res.metrics["clip"] = {k: meta.get(k) for k in ("clip_id", "category", "duration_s", "sample_rate",
                                                        "sha256", "reference_edited", "language", "model")}
        res.metrics["transcripts_shared_in_evidence"] = share
        ex, body = _transcribe(ctx, res.case_id, wav, p.language, p.model)
        res.exchanges.append(ex)
        # Full response kept ONLY in git-ignored evidence/private/<run>/ for offline WER analysis.
        ctx.save_private(f"{prompt_id}-stt-response.json", ex.body)
        res.check("HTTP 200", ex.status == 200, "200", ex.status, DOCUMENTED, D.STT_TRANSCRIBE)
        tx = (body or {}).get("transcription") if body else None
        if not isinstance(tx, str):
            return
        ref = meta["reference_transcript"]
        wer, cer = word_error_rate(ref, tx), char_error_rate(ref, tx)
        # No transcript hash: prompts are public, so a hash would let anyone confirm a guessed transcript.
        res.metrics.update({"wer": round(wer, 3), "cer": round(cer, 3)})
        if share:
            res.metrics.update({"transcription": tx, "reference": ref})
        if p.key_tokens:
            hits = key_token_hits(tx, [list(t) for t in p.key_tokens])
            res.metrics["key_tokens"] = hits
            res.check("expected key terms recognised", hits["hit"] == hits["total"], hits["total"],
                      f"{hits['hit']} found; missing {hits['missing']}", EXPLORATORY)
        if prompt_id == "H1":
            res.check("WER <= 0.25 on natural read speech", wer <= 0.25, "<= 0.25", round(wer, 3), QUALITY)
        # Evidence must not carry the speaker's words unless they opted in: strip the raw response body.
        if not share:
            for e in res.exchanges:
                e.body = json.dumps({"withheld": "human transcript not shared (no --share-transcript)",
                                     "status": (body or {}).get("status")}).encode()
    return run


_HUMAN_SPECS = [
    ("H1", "Human: natural English (replaces synthetic P2-STT-02, pulse-pro)", "pulse-pro"),
    ("H2", "Human: technical terminology (replaces synthetic P2-STT-03)", "pulse"),
    ("H3", "Human: numbers, currency, dates (replaces synthetic P2-STT-04)", "pulse"),
    ("H4", "Human: Hinglish, language=hi (replaces TTS-generated P2-STT-12)", "pulse"),
    ("H5", "Human: spontaneous speech (replaces synthetic P2-STT-08)", "pulse"),
]
P2_CASES.extend(
    _c(f"P2-HUM-0{i}", "3h", "P1", "STT accuracy (human)", title, QUALITY,
       "200; WER/CER vs speaker-confirmed reference; key terms recognised (no documented accuracy threshold)",
       (D.STT_TRANSCRIBE, D.STT_PULSE_CARD), 1, _human_case(pid), stt_audio_seconds=20.0)
    for i, (pid, title, _m) in enumerate(_HUMAN_SPECS, start=1))
P2_BY_ID.update({c.case_id: c for c in P2_CASES})

# Batch 3h = Batch 3 with five synthetic clips swapped for five human recordings: same 15-request budget.
BATCH_VARIANTS = {"3h": ["P2-STT-01", "P2-STT-05", "P2-STT-06", "P2-STT-07", "P2-STT-09", "P2-STT-10",
                         "P2-STT-11", "P2-STT-13", "P2-STT-14", "P2-STT-15",
                         "P2-HUM-01", "P2-HUM-02", "P2-HUM-03", "P2-HUM-04", "P2-HUM-05"]}
BATCHES = sorted({c.batch for c in P2_CASES if c.batch != "3h"}) + ["3h"]


def batch_cases(batch: str) -> list[CaseSpec]:  # noqa: F811 - extends the earlier definition with variants
    if batch in BATCH_VARIANTS:
        return [P2_BY_ID[i] for i in BATCH_VARIANTS[batch]]
    return [c for c in P2_CASES if c.batch == batch]
