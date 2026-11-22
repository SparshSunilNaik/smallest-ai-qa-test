"""Test case catalogue. Each case declares its documentation source, expected behaviour,
requirement provenance and planned request count, and implements bounded live checks."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import api
from . import docs_refs as D
from .audio import AudioFormatError, looks_like_mp3, parse_wav, pcm16_rms_dbfs
from .client import Exchange, QAClient
from .fixtures import Fixture
from .results import (
    CANDIDATE,
    DOC_AMBIGUITY,
    DOCUMENTED,
    EXPLORATORY,
    INCONCLUSIVE,
    NOT_TESTED,
    PASSED,
    QUALITY,
    CaseResult,
    auto_classify,
)
from .stats import summarize
from .textsim import normalize, word_error_rate

SHORT_EN = "Hello from the Smallest AI QA harness. This is a short synthesis test."
LATENCY_EN = "Thank you for calling. Your appointment is confirmed for tomorrow morning."
HINGLISH = "नमस्ते, मैं आपकी booking confirm करने के लिए call कर रही हूँ। Your slot is at ten AM."
SILENCE_FLOOR_DBFS = -50.0
MAX_WER = 0.25


@dataclass
class Context:
    client: QAClient
    run_id: str
    private_dir: Path
    fixture: Fixture | None = None
    state: dict[str, Any] = field(default_factory=dict)
    p2_fixtures: dict[str, Any] = field(default_factory=dict)
    listening: list[dict[str, Any]] = field(default_factory=list)  # clips queued for human listening

    def save_private(self, name: str, data: bytes) -> None:
        """Audio and raw bodies go to git-ignored evidence/private/ only."""
        if not data:
            return
        self.private_dir.mkdir(parents=True, exist_ok=True)
        (self.private_dir / name).write_bytes(data)


@dataclass(frozen=True)
class CaseSpec:
    case_id: str
    area: str
    title: str
    requirement: str
    expected: str
    doc_refs: tuple[str, ...]
    planned_requests: int
    run: Callable[[Context, CaseResult], None]
    optional: bool = False
    synth_chars: int = 0  # characters expected to be synthesised (cost estimate)
    stt_audio_requests: int = 0  # requests carrying the STT fixture (cost estimate)
    depends_on: tuple[str, ...] = ()
    phase: int = 1
    batch: str = ""
    priority: str = ""  # P0 (highest) .. P2
    stt_audio_seconds: float = 0.0  # Phase 2 cost estimate
    p2_fixtures: tuple[str, ...] = ()  # Phase 2 STT fixtures required
    requires_human: bool = False  # audio-content claims need listening confirmation
    max_requests: int | None = None  # upper bound when planned_requests is data-dependent


# ----------------------------------------------------------------------------- helpers

def _rid(ctx: Context, case_id: str) -> str:
    return f"qa-{case_id}-{ctx.run_id}"


def _error_shape(res: CaseResult, ex: Exchange, doc: str) -> None:
    body = ex.json()
    has_msg = isinstance(body, dict) and any(isinstance(body.get(k), str) and body.get(k) for k in ("error", "message"))
    res.check("error body is JSON with an `error` or `message` string", has_msg,
              "{error?: string, message?: string}", ex.body[:200].decode("utf-8", "replace") or "<empty>",
              DOCUMENTED, doc)


def _no_audio(res: CaseResult, ex: Exchange) -> None:
    is_audio = ex.body[:4] == b"RIFF" or looks_like_mp3(ex.body)
    res.check("no audio payload returned on rejection", not is_audio, "no audio bytes",
              "audio bytes present" if is_audio else "no audio", QUALITY)


def _rejected_400(res: CaseResult, ex: Exchange, doc: str) -> None:
    status = ex.status
    res.check("request rejected with a 4xx client error", status is not None and 400 <= status < 500,
              "4xx", status, DOCUMENTED, doc)
    res.check("status is the documented 400", status == 400, "400", status, DOCUMENTED, doc)
    _error_shape(res, ex, doc)
    _no_audio(res, ex)


def _wav_checks(res: CaseResult, ex: Exchange, sample_rate: int, ctx: Context, name: str) -> None:
    res.check("HTTP 200", ex.status == 200, "200", ex.status, DOCUMENTED, D.TTS_SYNC)
    res.check("response not truncated by harness cap", not ex.truncated, "complete body", f"{len(ex.body)} bytes",
              QUALITY)
    ctype = ex.content_type or "<none>"
    res.check("Content-Type is audio/*", ctype.startswith("audio/"), "audio/* (not specified in docs)", ctype,
              QUALITY)
    try:
        info = parse_wav(ex.body)
    except AudioFormatError as exc:
        res.check("body is a RIFF/WAVE container", False, "RIFF/WAVE (output_format=wav)", str(exc), DOCUMENTED,
                  D.TTS_SYNC)
        return
    ctx.save_private(name, ex.body)
    res.check("body is a RIFF/WAVE container", True, "RIFF/WAVE (output_format=wav)", "RIFF/WAVE", DOCUMENTED,
              D.TTS_SYNC)
    res.check("WAV sample rate equals requested sample_rate", info.sample_rate == sample_rate, sample_rate,
              info.sample_rate, DOCUMENTED, D.TTS_SYNC)
    res.check("audio duration plausible for short text (1-30 s)", 1.0 <= info.duration_s <= 30.0, "1-30 s",
              f"{info.duration_s:.2f} s", QUALITY)
    level = pcm16_rms_dbfs(ex.body[info.data_offset:]) if info.bits_per_sample == 16 else None
    res.check("audio is not silent", None if level is None else level > SILENCE_FLOOR_DBFS,
              f"RMS > {SILENCE_FLOOR_DBFS} dBFS", "n/a (non-16-bit)" if level is None else f"{level:.1f} dBFS",
              QUALITY)
    res.metrics.update({"wav_channels": info.channels, "wav_bits": info.bits_per_sample,
                        "wav_sample_rate": info.sample_rate, "audio_duration_s": round(info.duration_s, 3),
                        "rms_dbfs": None if level is None else round(level, 1)})


def _echo_check(res: CaseResult, ex: Exchange, sent: str) -> None:
    echoed = next((v for k, v in ex.headers.items() if k.lower() == "x-external-request-id"), None)
    res.check("X-External-Request-Id echoes request_id", echoed == sent, sent, echoed or "<absent>", DOCUMENTED,
              D.TTS_SYNC)


# ----------------------------------------------------------------------------- AUTH

def auth_valid(ctx: Context, res: CaseResult) -> None:
    ex = api.list_pro_voices(ctx.client, res.case_id)
    res.exchanges.append(ex)
    res.check("HTTP 200 with valid Bearer key", ex.status == 200, "200", ex.status, DOCUMENTED, D.AUTH)
    payload = ex.json()
    res.check("voice catalogue is JSON", payload is not None, "JSON (schema undocumented)", ex.content_type,
              QUALITY)
    ids = api.extract_voice_ids(payload) if payload is not None else set()
    ctx.state["pro_voice_ids"] = ids if payload is not None else None
    res.metrics["pro_voice_count"] = len(ids)
    res.check(f"documented Pro voice '{api.TTS_VOICE}' is listed", api.TTS_VOICE in ids if ids else None,
              f"'{api.TTS_VOICE}' present", f"{len(ids)} voice ids parsed", DOCUMENTED, D.TTS_SYNC)


def _auth_negative(ctx: Context, res: CaseResult, mode: str) -> None:
    ex = api.synthesize(ctx.client, res.case_id, api.tts_body(SHORT_EN), auth=mode, expect_auth_ok=False)  # type: ignore[arg-type]
    res.exchanges.append(ex)
    res.check("HTTP 401", ex.status == 401, "401", ex.status, DOCUMENTED, D.AUTH)
    _error_shape(res, ex, D.AUTH)
    _no_audio(res, ex)


def auth_missing(ctx: Context, res: CaseResult) -> None:
    _auth_negative(ctx, res, "none")


def auth_invalid(ctx: Context, res: CaseResult) -> None:
    _auth_negative(ctx, res, "invalid")


# ----------------------------------------------------------------------------- TTS

def tts_valid_wav(ctx: Context, res: CaseResult) -> None:
    rid = _rid(ctx, res.case_id)
    ex = api.synthesize(ctx.client, res.case_id, api.tts_body(SHORT_EN, request_id=rid))
    res.exchanges.append(ex)
    _wav_checks(res, ex, 24000, ctx, f"{res.case_id}.wav")
    _echo_check(res, ex, rid)


def tts_mp3(ctx: Context, res: CaseResult) -> None:
    ex = api.synthesize(ctx.client, res.case_id, api.tts_body(SHORT_EN, output_format="mp3"))
    res.exchanges.append(ex)
    res.check("HTTP 200", ex.status == 200, "200", ex.status, DOCUMENTED, D.TTS_SYNC)
    ok = looks_like_mp3(ex.body)
    res.check("body is MPEG audio (ID3 tag or frame sync)", ok, "MP3 (output_format=mp3)",
              ex.body[:4].hex() or "<empty>", DOCUMENTED, D.TTS_SYNC)
    res.check("body size > 1 KB", len(ex.body) > 1024, "> 1024 bytes", len(ex.body), QUALITY)
    ctype = ex.content_type or "<none>"
    res.check("Content-Type is audio/mpeg", ctype.startswith("audio/mpeg"), "audio/mpeg (not specified in docs)",
              ctype, QUALITY)
    if ok:
        ctx.save_private(f"{res.case_id}.mp3", ex.body)


def _tts_reject(text: str | None = None, **over: Any) -> Callable[[Context, CaseResult], None]:
    def run(ctx: Context, res: CaseResult) -> None:
        body = api.tts_body(SHORT_EN if text is None else text, **over)
        ex = api.synthesize(ctx.client, res.case_id, body)
        res.exchanges.append(ex)
        _rejected_400(res, ex, D.TTS_SYNC)
    return run


def tts_voice_model_mismatch(ctx: Context, res: CaseResult) -> None:
    ids = ctx.state.get("pro_voice_ids")
    if not ids:
        res.notes.append("Pro voice catalogue unavailable from AUTH-01; cannot pick a provably non-Pro voice.")
        res.classification = NOT_TESTED
        return
    voice = next((v for v in api.NON_PRO_VOICE_CANDIDATES if v not in ids), None)
    if voice is None:
        res.notes.append("All candidate non-Pro voices appear in the Pro catalogue; probe not meaningful.")
        res.classification = NOT_TESTED
        return
    res.metrics["probe_voice"] = voice
    ex = api.synthesize(ctx.client, res.case_id, api.tts_body(SHORT_EN, voice_id=voice))
    res.exchanges.append(ex)
    res.check("mismatched voice/model rejected with 400 (API reference + 2026-11-05 changelog)", ex.status == 400,
              "400", ex.status, DOCUMENTED, D.CHANGELOG_2026_11_05)
    expected_msg = f"Voice '{voice}' is not available on the lightning_v3.1_pro model"
    text = ex.body[:400].decode("utf-8", "replace")
    res.check("error names the voice and model", expected_msg.lower() in text.lower(), expected_msg,
              text or "<empty>", DOCUMENTED, D.TTS_SYNC)
    if ex.status == 200:
        ctx.save_private(f"{res.case_id}.wav", ex.body)
    base = auto_classify(res)
    if base == INCONCLUSIVE:
        res.classification = INCONCLUSIVE
    elif ex.status == 400:
        res.classification = DOC_AMBIGUITY
        res.notes.append("Behaviour matches the API reference/changelog; the Lightning v3.1 Pro model card FAQ "
                         "states mismatched pairings are not rejected, which this observation contradicts.")
    else:
        res.classification = CANDIDATE


def tts_length_boundary(ctx: Context, res: CaseResult) -> None:
    text = ("a" * 7999) + "bc"  # 8001 non-whitespace characters, one over the documented max
    body = api.tts_body(text, sample_rate=8000, output_format="mp3")
    ex = api.synthesize(ctx.client, res.case_id, body)
    res.exchanges.append(ex)
    _rejected_400(res, ex, D.TTS_SYNC)


def tts_hinglish(ctx: Context, res: CaseResult) -> None:
    ex = api.synthesize(ctx.client, res.case_id, api.tts_body(HINGLISH, language="hi"))
    res.exchanges.append(ex)
    _wav_checks(res, ex, 24000, ctx, f"{res.case_id}.wav")
    res.notes.append("Pronunciation quality of code-switched audio requires human listening; saved privately.")


# ----------------------------------------------------------------------------- STT

def _stt_params(model: str = "pulse", **extra: str) -> dict[str, str]:
    return {"model": model, "language": "en", **extra}


def _stt_success_checks(res: CaseResult, ex: Exchange, fx: Fixture) -> dict | None:
    res.check("HTTP 200", ex.status == 200, "200", ex.status, DOCUMENTED, D.STT_TRANSCRIBE)
    body = ex.json()
    res.check("response is a JSON object", isinstance(body, dict), "JSON object", ex.content_type, DOCUMENTED,
              D.STT_TRANSCRIBE)
    if not isinstance(body, dict):
        return None
    res.check("status == 'success'", body.get("status") == "success", "success", body.get("status"), DOCUMENTED,
              D.STT_TRANSCRIBE)
    tx = body.get("transcription")
    res.check("transcription is a non-empty string", isinstance(tx, str) and bool(tx.strip()), "non-empty string",
              repr(tx)[:120], DOCUMENTED, D.STT_TRANSCRIBE)
    if isinstance(tx, str):
        wer = word_error_rate(fx.reference_text, tx)
        res.metrics["wer"] = round(wer, 3)
        res.metrics["transcription"] = tx
        res.check(f"WER vs reference <= {MAX_WER} (clean synthetic speech)", wer <= MAX_WER, f"<= {MAX_WER}",
                  round(wer, 3), QUALITY)
    duration = (body.get("metadata") or {}).get("duration") if isinstance(body.get("metadata"), dict) else None
    res.check("metadata.duration present and within 0.5 s of fixture",
              isinstance(duration, (int, float)) and abs(duration - fx.duration_s) <= 0.5,
              f"{fx.duration_s:.2f} s +/- 0.5", duration, QUALITY, D.STT_TRANSCRIBE)
    return body


def stt_success(ctx: Context, res: CaseResult) -> None:
    fx = ctx.fixture
    assert fx is not None
    res.metrics["fixture"] = fx.describe()
    ex = api.transcribe(ctx.client, res.case_id, fx.path.read_bytes(), _stt_params())
    res.exchanges.append(ex)
    body = _stt_success_checks(res, ex, fx)
    if body is not None:
        for key in ("words", "utterances"):
            res.check(f"Pulse response includes `{key}` array", isinstance(body.get(key), list), "array",
                      type(body.get(key)).__name__, DOCUMENTED, D.STT_TRANSCRIBE)
        if isinstance(body.get("transcription"), str):
            ctx.state.setdefault("stt_transcripts", []).append(body["transcription"])


def stt_schema_pro(ctx: Context, res: CaseResult) -> None:
    fx = ctx.fixture
    assert fx is not None
    ex = api.transcribe(ctx.client, res.case_id, fx.path.read_bytes(),
                        _stt_params("pulse-pro", word_timestamps="true"))
    res.exchanges.append(ex)
    body = _stt_success_checks(res, ex, fx)
    if body is None:
        return
    meta = body.get("metadata") if isinstance(body.get("metadata"), dict) else {}
    for key in ("language", "request_id"):
        res.check(f"Pulse Pro field `{key}` present", key in body, "present", "present" if key in body else "absent",
                  DOCUMENTED, D.STT_TRANSCRIBE)
    for key in ("duration", "processing_time_ms", "rtfx", "num_chunks"):
        res.check(f"metadata.{key} present", key in meta, "present", meta.get(key, "absent"), DOCUMENTED,
                  D.STT_TRANSCRIBE)
    words = body.get("words")
    res.check("words[] non-empty with word_timestamps=true", isinstance(words, list) and len(words) > 0,
              "non-empty array", len(words) if isinstance(words, list) else type(words).__name__, DOCUMENTED,
              D.STT_TRANSCRIBE)
    if not isinstance(words, list) or not words:
        return
    well_formed = all(isinstance(w, dict) and {"word", "start", "end", "confidence"} <= w.keys() for w in words)
    res.check("each word has word/start/end/confidence", well_formed, "all keys present", well_formed, DOCUMENTED,
              D.STT_TRANSCRIBE)
    if not well_formed:
        return
    conf_ok = all(isinstance(w["confidence"], (int, float)) and 0 <= w["confidence"] <= 1 for w in words)
    res.check("confidence within [0, 1]", conf_ok, "0..1", conf_ok, DOCUMENTED, D.STT_TRANSCRIBE)
    spans_ok = all(w["start"] <= w["end"] for w in words)
    res.check("start <= end for every word", spans_ok, True, spans_ok, QUALITY)
    mono = all(a["start"] <= b["start"] for a, b in zip(words, words[1:]))
    res.check("word start times non-decreasing", mono, True, mono, QUALITY)
    last_end = words[-1]["end"]
    res.check("last word ends within audio duration (+0.25 s)", last_end <= fx.duration_s + 0.25,
              f"<= {fx.duration_s + 0.25:.2f}", last_end, QUALITY)
    res.metrics["word_count"] = len(words)


def stt_consistency(ctx: Context, res: CaseResult) -> None:
    fx = ctx.fixture
    assert fx is not None
    prior = list(ctx.state.get("stt_transcripts", []))[:1]
    needed = 3 - len(prior)
    res.metrics["reused_samples_from_STT-01"] = len(prior)
    transcripts = list(prior)
    audio = fx.path.read_bytes()
    for _ in range(needed):
        ex = api.transcribe(ctx.client, res.case_id, audio, _stt_params())
        res.exchanges.append(ex)
        body = ex.json()
        res.check("HTTP 200", ex.status == 200, "200", ex.status, DOCUMENTED, D.STT_TRANSCRIBE)
        if isinstance(body, dict) and isinstance(body.get("transcription"), str):
            transcripts.append(body["transcription"])
    res.metrics["transcripts"] = transcripts
    res.metrics["sample_count"] = len(transcripts)
    if len(transcripts) < 2:
        res.check("at least two transcripts to compare", None, ">= 2", len(transcripts), EXPLORATORY)
        return
    norm = {" ".join(normalize(t)) for t in transcripts}
    res.check("identical input yields identical normalised transcript", len(norm) == 1, "1 distinct transcript",
              f"{len(norm)} distinct", EXPLORATORY)
    wers = [word_error_rate(fx.reference_text, t) for t in transcripts]
    res.metrics["wer_per_sample"] = [round(w, 3) for w in wers]


def _stt_reject(params: dict[str, str], audio: str = "fixture") -> Callable[[Context, CaseResult], None]:
    def run(ctx: Context, res: CaseResult) -> None:
        data = b"" if audio == "empty" else ctx.fixture.path.read_bytes()  # type: ignore[union-attr]
        ex = api.transcribe(ctx.client, res.case_id, data, params)
        res.exchanges.append(ex)
        status = ex.status
        res.check("request rejected with a 4xx client error", status is not None and 400 <= status < 500, "4xx",
                  status, DOCUMENTED, D.STT_TRANSCRIBE)
        res.check("status is the documented 400", status == 400, "400", status, DOCUMENTED, D.STT_TRANSCRIBE)
        body = ex.json()
        has_msg = isinstance(body, dict) and any(body.get(k) for k in ("message", "error", "errors", "error_code"))
        res.check("JSON error body with message/error/errors", has_msg, "documented error fields",
                  ex.body[:200].decode("utf-8", "replace") or "<empty>", DOCUMENTED, D.STT_TRANSCRIBE)
    return run


# ----------------------------------------------------------------------------- Streaming

def _sse_checks(res: CaseResult, ex: Exchange, obs: api.StreamObservation) -> None:
    res.check("HTTP 200", ex.status == 200, "200", ex.status, DOCUMENTED, D.TTS_STREAMING)
    ctype = ex.content_type or "<none>"
    res.check("Content-Type is text/event-stream", ctype.startswith("text/event-stream"), "text/event-stream",
              ctype, QUALITY)
    res.check("all frames carry JSON data", obs.invalid_frames == 0 and bool(obs.frames), "0 invalid frames",
              f"{obs.invalid_frames} invalid / {len(obs.frames)} total", DOCUMENTED, D.TTS_STREAMING)
    audio_frames = [f for f in obs.frames if f.get("audio_b64_chars")]
    res.check(">= 1 audio chunk before completion", len(audio_frames) >= 1, ">= 1", len(audio_frames), DOCUMENTED,
              D.TTS_STREAMING)
    res.check("all audio chunks are valid base64", obs.undecodable_audio == 0, 0, obs.undecodable_audio,
              DOCUMENTED, D.TTS_STREAMING)
    every_done = all("done" in f for f in obs.frames) if obs.frames else False
    res.check("every frame has a `done` field", every_done, True, every_done, DOCUMENTED, D.TTS_STREAMING)
    terminals = [i for i, f in enumerate(obs.frames) if f.get("done") is True]
    last_ok = bool(terminals) and terminals == [len(obs.frames) - 1]
    res.check("exactly one done:true frame and it is last", last_ok, "1 terminal frame, last",
              f"terminal indices {terminals} of {len(obs.frames)}", DOCUMENTED, D.TTS_STREAMING)
    if terminals:
        status = obs.frames[terminals[0]].get("status")
        res.check("terminal frame status == '200'", str(status) == "200", "200", status, DOCUMENTED,
                  D.TTS_STREAMING)
    res.check("no frames after terminal / no unterminated trailing data",
              obs.frames_after_done == 0 and obs.trailing_unparsed_bytes == 0, "0 / 0",
              f"{obs.frames_after_done} / {obs.trailing_unparsed_bytes}", QUALITY)
    res.metrics.update({
        "frames": len(obs.frames), "audio_chunks": len(obs.audio_chunks), "audio_bytes": len(obs.audio),
        "ttfb_ms": ex.ttfb_ms and round(ex.ttfb_ms, 1),
        "first_audio_event_ms": obs.first_audio_ms and round(obs.first_audio_ms, 1),
        "done_event_ms": obs.done_ms and round(obs.done_ms, 1),
        "stream_closed_ms": ex.duration_ms and round(ex.duration_ms, 1),
    })
    if obs.done_ms is not None and ex.duration_ms is not None:
        res.metrics["close_after_done_ms"] = round(ex.duration_ms - obs.done_ms, 1)


def stream_pcm(ctx: Context, res: CaseResult) -> None:
    ex, obs = api.stream_sse(ctx.client, res.case_id, api.tts_body(SHORT_EN, output_format="pcm"))
    res.exchanges.append(ex)
    _sse_checks(res, ex, obs)
    pcm = obs.audio
    res.check("decoded PCM is non-empty and 16-bit aligned", len(pcm) > 0 and len(pcm) % 2 == 0,
              "even byte count > 0", len(pcm), QUALITY)
    if pcm:
        level = pcm16_rms_dbfs(pcm)
        res.check("streamed audio is not silent", level > SILENCE_FLOOR_DBFS, f"> {SILENCE_FLOOR_DBFS} dBFS",
                  f"{level:.1f} dBFS", QUALITY)
        res.metrics["audio_duration_s_assuming_24k_mono16"] = round(len(pcm) / 2 / 24000, 3)
        ctx.save_private(f"{res.case_id}.pcm", pcm)


def stream_wav(ctx: Context, res: CaseResult) -> None:
    ex, obs = api.stream_sse(ctx.client, res.case_id, api.tts_body(SHORT_EN, output_format="wav"))
    res.exchanges.append(ex)
    _sse_checks(res, ex, obs)
    if not obs.audio_chunks:
        return
    first_hdr = obs.audio_chunks[0][:4] == b"RIFF"
    later_hdrs = sum(1 for c in obs.audio_chunks[1:] if c[:4] == b"RIFF")
    res.check("first audio chunk starts with a WAV header", first_hdr, "RIFF", obs.audio_chunks[0][:4].hex(),
              DOCUMENTED, D.CHANGELOG_2026_11_05)
    res.check("only one WAV header in the stream", later_hdrs == 0, "0 additional headers", later_hdrs,
              DOCUMENTED, D.CHANGELOG_2026_11_05)
    try:
        info = parse_wav(obs.audio)
        res.check("concatenated stream parses as 24 kHz WAV", info.sample_rate == 24000, 24000, info.sample_rate,
                  QUALITY)
        res.metrics["declared_wav_data_bytes"] = info.declared_data_bytes
        ctx.save_private(f"{res.case_id}.wav", obs.audio)
    except AudioFormatError as exc:
        res.check("concatenated stream parses as 24 kHz WAV", False, "valid WAV", str(exc), QUALITY)


# ----------------------------------------------------------------------------- Latency

LATENCY_SAMPLES = 5


def latency_streaming(ctx: Context, res: CaseResult) -> None:
    ttfb, first_audio, total = [], [], []
    for i in range(LATENCY_SAMPLES):
        ex, obs = api.stream_sse(ctx.client, res.case_id, api.tts_body(LATENCY_EN, output_format="pcm"))
        res.exchanges.append(ex)
        ok = ex.status == 200 and obs.done_ms is not None
        res.check(f"sample {i + 1}: HTTP 200 and stream completed", ok, "200 + done", ex.status, DOCUMENTED,
                  D.TTS_STREAMING)
        if ok:
            ttfb.append(ex.ttfb_ms)
            first_audio.append(obs.first_audio_ms)
            total.append(ex.duration_ms)
    res.metrics.update({
        "method": "sequential, concurrency 1, client-side wall clock incl. network; nearest-rank p95",
        "ttfb_ms": summarize(ttfb), "first_audio_event_ms": summarize(first_audio), "total_ms": summarize(total),
        "raw_ttfb_ms": [round(v, 1) for v in ttfb], "raw_first_audio_ms": [round(v, 1) for v in first_audio if v],
        "raw_total_ms": [round(v, 1) for v in total],
    })
    res.notes.append(f"n={len(total)} successful samples; p95 with n<=20 equals an order statistic near the max and "
                     "is not a stable estimate. No SLO is documented, so no pass/fail threshold is asserted.")


# ----------------------------------------------------------------------------- Catalogue

_E = "Empty/whitespace-only text is rejected (text required; 'whitespace-only rejected')"

CASES: list[CaseSpec] = [
    CaseSpec("AUTH-01", "Authentication", "Valid credentials accepted (Pro voice catalogue)", DOCUMENTED,
             "200 with JSON voice catalogue containing documented voice 'meher'", (D.AUTH, D.DEPRECATIONS), 1,
             auth_valid),
    CaseSpec("AUTH-02", "Authentication", "Missing Authorization header rejected", DOCUMENTED,
             "401 with JSON error body; no audio, no synthesis", (D.AUTH, D.ERROR_REFERENCE), 1, auth_missing),
    CaseSpec("AUTH-03", "Authentication", "Invalid API key rejected", DOCUMENTED,
             "401 with JSON error body; no audio", (D.AUTH, D.ERROR_REFERENCE), 1, auth_invalid),
    CaseSpec("TTS-01", "TTS", "Valid short synthesis (lightning_v3.1_pro / meher / wav 24 kHz)", DOCUMENTED,
             "200, RIFF/WAVE at 24 kHz, non-silent, X-External-Request-Id echoed", (D.TTS_SYNC,), 1, tts_valid_wav,
             synth_chars=len(SHORT_EN)),
    CaseSpec("TTS-02", "TTS", "Response format: output_format=mp3", DOCUMENTED,
             "200 with MPEG audio bytes", (D.TTS_SYNC,), 1, tts_mp3, synth_chars=len(SHORT_EN)),
    CaseSpec("TTS-03", "TTS", "Empty text rejected", DOCUMENTED, f"400 + error body. {_E}", (D.TTS_SYNC,), 1,
             _tts_reject("")),
    CaseSpec("TTS-04", "TTS", "Whitespace-only text rejected", DOCUMENTED, f"400 + error body. {_E}",
             (D.TTS_SYNC,), 1, _tts_reject("   \n\t   ")),
    CaseSpec("TTS-05", "TTS", "Unknown voice_id rejected", DOCUMENTED, "400 + error body, no audio",
             (D.TTS_SYNC,), 1, _tts_reject(voice_id="qa_nonexistent_voice_zz9")),
    CaseSpec("TTS-06", "TTS", "Unknown model rejected", DOCUMENTED, "400 (model is an enum) + error body",
             (D.TTS_SYNC,), 1, _tts_reject(model="lightning_qa_nonexistent")),
    CaseSpec("TTS-07", "TTS", "Voice/model mismatch (non-Pro voice on lightning_v3.1_pro)", DOCUMENTED,
             "400 'Voice <id> is not available on the lightning_v3.1_pro model' (API ref, changelog); model card "
             "FAQ says mismatches are not rejected -> documentation conflict probe",
             (D.TTS_SYNC, D.CHANGELOG_2026_11_05, D.TTS_PRO_CARD), 1, tts_voice_model_mismatch,
             depends_on=("AUTH-01",)),
    CaseSpec("TTS-08", "TTS", "Text length boundary: 8001 chars (max 8000)", DOCUMENTED,
             "400 for text over 8000 characters after trim", (D.TTS_SYNC,), 1, tts_length_boundary, optional=True,
             synth_chars=0),
    CaseSpec("TTS-09", "TTS", "Hindi-English code-switched text (meher, language=hi)", DOCUMENTED,
             "200, valid 24 kHz WAV, non-silent", (D.TTS_SYNC, D.TTS_PRO_CARD), 1, tts_hinglish,
             synth_chars=len(HINGLISH)),
    CaseSpec("STR-01", "Streaming", "SSE streaming success, framing, completion, TTFB (pcm)", DOCUMENTED,
             "200 text/event-stream; JSON frames with base64 audio and done:false; single final "
             "{status:'200', done:true}", (D.TTS_STREAMING,), 1, stream_pcm, synth_chars=len(SHORT_EN)),
    CaseSpec("STR-02", "Streaming", "SSE wav: single header on first chunk", DOCUMENTED,
             "first decoded chunk starts with RIFF; no later headers", (D.TTS_STREAMING, D.CHANGELOG_2026_11_05),
             1, stream_wav, synth_chars=len(SHORT_EN)),
    CaseSpec("STT-01", "STT", "Pulse transcription of self-created 16 kHz WAV", DOCUMENTED,
             "200, status=success, non-empty transcription, WER <= 0.25, words/utterances arrays",
             (D.STT_QUICKSTART, D.STT_TRANSCRIBE), 1, stt_success, stt_audio_requests=1),
    CaseSpec("STT-02", "STT", "Pulse Pro response schema with word_timestamps=true", DOCUMENTED,
             "documented Pulse Pro fields; words[] with word/start/end/confidence in [0,1]",
             (D.STT_TRANSCRIBE,), 1, stt_schema_pro, stt_audio_requests=1),
    CaseSpec("STT-03", "STT", "Invalid model query parameter rejected", DOCUMENTED,
             "400 ('Missing or invalid' model)", (D.STT_TRANSCRIBE,), 1,
             _stt_reject({"model": "pulse-qa-nonexistent", "language": "en"})),
    CaseSpec("STT-04", "STT", "Non-lowercase boolean (word_timestamps=yes) rejected", DOCUMENTED,
             "400 (only lowercase 'true'/'false' accepted)", (D.STT_TRANSCRIBE,), 1,
             _stt_reject({"model": "pulse", "language": "en", "word_timestamps": "yes"})),
    CaseSpec("STT-05", "STT", "Empty audio body rejected", DOCUMENTED, "400 (empty audio)", (D.STT_TRANSCRIBE,), 1,
             _stt_reject({"model": "pulse", "language": "en"}, audio="empty")),
    CaseSpec("STT-06", "STT", "Consistency across identical requests (3 samples incl. STT-01)", EXPLORATORY,
             "Exploratory: identical normalised transcripts (determinism is not documented)", (D.STT_TRANSCRIBE,),
             2, stt_consistency, stt_audio_requests=2, depends_on=("STT-01",)),
    CaseSpec("LAT-01", "Latency", f"Exploratory SSE latency, {LATENCY_SAMPLES} sequential samples", EXPLORATORY,
             "Measure TTFB, first-audio and total time; report median and nearest-rank p95; no SLO asserted",
             (D.TTS_STREAMING, D.CONCURRENCY), LATENCY_SAMPLES, latency_streaming,
             synth_chars=LATENCY_SAMPLES * len(LATENCY_EN)),
]

CASES_BY_ID = {c.case_id: c for c in CASES}
