"""Phase 2 harness tests: ledger migration, caps, contracts, fixtures, WS, SDK, doc examples, batches."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path

import httpx
import pytest
from fake_api import VALID_KEY
from fake_api_p2 import FakeP2, start_ws_server, tone_pcm, wav_of

from smallest_qa.audio import analyze_pcm16, mulaw_to_pcm16, pcm16_to_wav, wav_pcm16
from smallest_qa.budget import BudgetExceeded, RequestLedger
from smallest_qa.cases_p2 import BATCHES, P2_CASES, batch_cases, planned
from smallest_qa.config import REPO_ROOT, Settings
from smallest_qa.contract import conformance, human_message, signature
from smallest_qa.fixtures_p2 import RECIPES, P2Fixture
from smallest_qa.results import CANDIDATE, DOC_AMBIGUITY, NOT_TESTED, PASSED
from smallest_qa.runner import check_batch, execute, ledger_for

os.environ["SMALLESTAI_TELEMETRY"] = "0"
PHASE1_LEDGER_PREFIX_SHA = "b955fc45ed25989d9ac4a3e3cd150ea5670641152e26d25aa4b92ca0033ee474"


# ----------------------------------------------------------------------------- evidence preservation
def test_phase1_ledger_prefix_and_run_files_unchanged():
    ledger = REPO_ROOT / "evidence" / "request-ledger.jsonl"
    lines = ledger.read_bytes().splitlines(keepends=True)
    assert hashlib.sha256(b"".join(lines[:28])).hexdigest() == PHASE1_LEDGER_PREFIX_SHA
    for line in (REPO_ROOT / "evidence" / "phase1-manifest.sha256").read_text().splitlines():
        if line.startswith("#") or "[lines" in line:
            continue
        digest, rel = line.split("  ", 1)
        assert hashlib.sha256((REPO_ROOT / rel).read_bytes()).hexdigest() == digest, rel


# ----------------------------------------------------------------------------- ledger v2 + caps
def _ledger(tmp_path, max_requests=128):
    return RequestLedger(tmp_path / "l.jsonl", max_requests, phase_caps={1: 28, 2: 100}, phase_usd_caps={2: 2.0})


def test_v1_entries_are_phase1_and_v2_appends_without_rewriting(tmp_path):
    led = _ledger(tmp_path)
    for _ in range(28):
        led.reserve(run_id="r", case_id="X", method="GET", path="/p")
    before = led.path.read_bytes()
    assert "phase" not in json.loads(before.splitlines()[0])  # v1 format preserved for phase 1
    led.reserve(run_id="r2", case_id="P2", method="POST", path="/t", phase=2, batch="1", est_tts_chars=140)
    assert led.path.read_bytes().startswith(before)
    assert led.phase_used(1) == 28 and led.phase_used(2) == 1
    with pytest.raises(BudgetExceeded, match="Phase 1"):
        led.reserve(run_id="r", case_id="X", method="GET", path="/p")  # phase 1 is closed


def test_phase2_request_and_spend_caps(tmp_path):
    led = _ledger(tmp_path)
    with pytest.raises(BudgetExceeded, match="spend cap"):
        led.reserve(run_id="r", case_id="BIG", method="POST", path="/t", phase=2, est_tts_chars=10_000_000)
    small = RequestLedger(tmp_path / "s.jsonl", 128, phase_caps={2: 2})
    small.reserve(run_id="r", case_id="a", method="GET", path="/", phase=2)
    small.reserve(run_id="r", case_id="b", method="GET", path="/", phase=2)
    with pytest.raises(BudgetExceeded, match="Phase 2 request cap"):
        small.reserve(run_id="r", case_id="c", method="GET", path="/", phase=2)


def test_catalogue_batches_respect_limits():
    assert all(sum(planned(c) for c in batch_cases(b)) <= 20 for b in BATCHES)
    assert sum(planned(c) for c in P2_CASES) <= 92  # leaves >= 8 of the 100 for reproduction
    assert len({c.case_id for c in P2_CASES}) == len(P2_CASES)
    assert all(c.doc_refs and c.expected for c in P2_CASES)


def test_check_batch_refuses_oversized(settings):
    s = Settings(**{**settings.__dict__, "max_requests": 128})
    assert check_batch(s, P2_CASES, 2)  # all 90 at once must be refused
    assert check_batch(s, batch_cases("1"), 2) == []


# ----------------------------------------------------------------------------- contracts
def test_contract_flags_array_error_and_accepts_documented_shapes():
    live_f1 = {"error": [{"code": "too_small", "message": "Text cannot be empty", "path": ["text"]}]}
    ok, problems = conformance(live_f1, "tts")
    assert not ok and any("`error` is list" in p for p in problems)
    assert conformance({"error": "bad", "message": "bad"}, "tts") == (True, [])
    assert conformance({"status": "error", "message": "x", "errors": [{"path": ["m"]}]}, "stt")[0]
    assert signature(live_f1) == "{error:list[object{code,message,path}]}"
    assert human_message(live_f1) == "Text cannot be empty"


# ----------------------------------------------------------------------------- audio helpers
def test_analysis_detects_internal_gap_and_mulaw_roundtrip():
    rate = 16000
    pcm = tone_pcm("a", rate, 0.5) + b"\x00\x00" * (rate * 2) + tone_pcm("a", rate, 0.5)
    a = analyze_pcm16(pcm, rate)
    assert 1900 <= a["longest_internal_silence_ms"] <= 2100 and not a["all_silent"]
    assert mulaw_to_pcm16(bytes([0xFF]))[:2] == b"\x00\x00"  # mu-law 0xFF decodes to zero
    data, r = wav_pcm16(pcm16_to_wav(pcm, rate))
    assert data == pcm and r == rate


def test_recipes_are_complete_and_documented():
    ids = [r.fixture_id for r in RECIPES]
    assert len(ids) == len(set(ids)) == 15
    for r in RECIPES:
        assert r.description and r.language and (r.parts or r.source_file)


# ----------------------------------------------------------------------------- end-to-end batches
def _fixture_provider(fake: FakeP2, tmp_path: Path):
    def provide(ids):
        out = {}
        for r in RECIPES:
            if r.fixture_id not in ids:
                continue
            rate = 16000
            if r.category == "silence":
                pcm = b"\x00\x00" * rate * 3
            else:
                pcm = tone_pcm(r.reference, rate, 2.0)
            segs = [{"kind": "say", "start_s": 0.0, "end_s": 1.0, "voiced_start_s": 0.0, "voiced_end_s": 0.25},
                    {"kind": "say", "start_s": 1.0, "end_s": 2.0, "voiced_start_s": 0.3, "voiced_end_s": 2.0}]
            data = wav_of(pcm, rate)
            path = tmp_path / f"{r.fixture_id}.wav"
            path.write_bytes(data)
            fake.register(data, r.reference)
            out[r.fixture_id] = P2Fixture(r, path, hashlib.sha256(data).hexdigest(), len(data),
                                          len(pcm) / 2 / rate, rate, segs, analyze_pcm16(pcm, rate))
        return out
    return provide


def _run_batch(settings, fixture_wav, fake, batch, tmp_path, ws_url=None):
    s = Settings(**{**settings.__dict__, "max_requests": 128,
                    **({"base_url": ws_url} if ws_url else {})})
    fake.register(fixture_wav.path.read_bytes(), fixture_wav.reference_text)
    run_dir = execute(s, batch_cases(batch), transport=fake.transport(), sleep=lambda x: None, log=lambda *a: None,
                      fixture_provider=lambda: fixture_wav, phase=2, batch=batch,
                      p2_fixture_provider=_fixture_provider(fake, tmp_path), doc_example_mode="skip")
    payload = json.loads((run_dir / "results.json").read_text())
    return {c["case_id"]: c for c in payload["cases"]}, payload, s


def test_batch1_f2_isolation_sdk_and_contracts(settings, fixture_wav, tmp_path):
    logging.disable(logging.WARNING)
    fake = FakeP2(deviations={"zod_errors"})
    cases, payload, s = _run_batch(settings, fixture_wav, fake, "1", tmp_path)
    assert cases["P2-F2-03"]["classification"] == PASSED  # magnus works on its own model
    assert cases["P2-F2-03"]["metrics"]["voice"] == "magnus"
    assert cases["P2-F2-04"]["metrics"]["voice_in_v31_catalogue"] is True
    # array-shaped error bodies violate the documented TTS schema -> candidate
    for cid in ("P2-F2-04", "P2-ERR-01", "P2-ERR-04", "P2-ERR-05", "P2-ERR-06"):
        assert cases[cid]["classification"] == CANDIDATE, cid
    assert cases["P2-F2-05"]["classification"] == PASSED  # model omitted -> chosen from voice
    assert cases["P2-SDK-01"]["classification"] == PASSED
    assert cases["P2-SDK-02"]["classification"] == CANDIDATE  # SDK yields 0 items for documented frames
    assert cases["P2-SDK-02"]["metrics"]["server_audio_frames_on_wire"] > 0
    assert cases["P2-SDK-03"]["classification"] == PASSED
    assert all(cases[c]["classification"] == NOT_TESTED for c in ("P2-DOC-01", "P2-DOC-02", "P2-DOC-03"))
    led = ledger_for(s)
    assert led.phase_used(2) == len(fake.calls) == payload["requests_this_run"] == 15
    text = (Path(payload and s.evidence_dir) / "runs" / payload["run_id"] / "results.json").read_text()
    assert VALID_KEY not in text


def test_batch1_documented_fake_passes_contracts(settings, fixture_wav, tmp_path):
    logging.disable(logging.WARNING)
    cases, _, _ = _run_batch(settings, fixture_wav, FakeP2(), "1", tmp_path)
    for cid in ("P2-F2-04", "P2-F2-06", "P2-ERR-01", "P2-ERR-04", "P2-ERR-05", "P2-ERR-06"):
        assert cases[cid]["classification"] == PASSED, (cid, [c for c in cases[cid]["checks"] if not c["passed"]])


def test_batch2_streaming_ws_and_cancellation(settings, fixture_wav, tmp_path):
    server, url = start_ws_server()
    try:
        cases, payload, _ = _run_batch(settings, fixture_wav, FakeP2(), "2", tmp_path, ws_url=url)
    finally:
        server.shutdown()
    ws = cases["P2-WS-01"]
    assert ws["classification"] == PASSED, [c for c in ws["checks"] if not c["passed"]]
    assert ws["metrics"]["frame_status_counts"]["complete"] == 1
    assert cases["P2-WS-02"]["metrics"]["error_frame_signature"].startswith("{message:string")
    cancel = cases["P2-STR-05"]
    assert cancel["metrics"]["cancelled_stream"]["cancelled_by_client"] is True
    assert cancel["metrics"]["follow_up_probes"][0]["status"] == 200 and len(cancel["requests"]) == 2
    assert cases["P2-STR-01"]["metrics"]["underrun"]["max_playback_stall_ms"] == 0
    assert cases["P2-ERR-14"]["classification"] == PASSED  # AudioDecodeError code present
    assert cases["P2-STR-03"]["checks"][0]["passed"] is True
    assert payload["requests_this_run"] <= 19


def test_batch3_stt_fixtures_and_silence(settings, fixture_wav, tmp_path):
    cases, _, _ = _run_batch(settings, fixture_wav, FakeP2(), "3", tmp_path)
    assert cases["P2-STT-01"]["metrics"]["wer"] == 0.0
    assert cases["P2-STT-09"]["classification"] == PASSED  # empty transcript for silence
    assert cases["P2-STT-14"]["metrics"]["speakers"] == [0, 1]


class _Hallucinating(FakeP2):
    def register(self, audio, text):
        super().register(audio, text or "thank you for watching")  # words on non-speech input


def test_silence_hallucination_is_flagged(settings, fixture_wav, tmp_path):
    cases, _, _ = _run_batch(settings, fixture_wav, _Hallucinating(), "3", tmp_path)
    assert cases["P2-STT-09"]["classification"] == CANDIDATE
    assert any(c["name"].startswith("no hallucinated") and c["passed"] is False for c in cases["P2-STT-09"]["checks"])


def test_batches_4_to_6_run_and_queue_listening(settings, fixture_wav, tmp_path):
    for b in ("4", "5", "6"):
        cases, payload, s = _run_batch(settings, fixture_wav, FakeP2(), b, tmp_path)
        assert all(c["classification"] != NOT_TESTED for c in cases.values()), b
        if b in ("4", "5"):
            assert payload["listening_queue"]
            sheet = s.evidence_dir.parent / "reports" / "listening" / f"{payload['run_id']}-sheet.csv"
            assert sheet.exists() and "intelligible_1to5" in sheet.read_text()
    assert cases["P2-LAT-02"]["metrics"]["ttfb_ms"]["n"] == 5


# ----------------------------------------------------------------------------- SDK + doc examples offline
def test_sdk_offline_replay_detects_type_mismatch_and_sse_drop(tmp_path):
    from smallest_qa.sdk_tools import offline_checks

    logging.disable(logging.WARNING)
    ev = tmp_path / "evidence"
    run = ev / "runs" / "R1"
    run.mkdir(parents=True)
    body = json.dumps({"error": [{"code": "too_small", "message": "Text cannot be empty", "path": ["text"]}]})
    run.joinpath("results.json").write_text(json.dumps({"run_id": "R1", "cases": [{"case_id": "X", "requests": [
        {"status": 400, "endpoint": "/waves/v1/tts", "body_excerpt": body, "request_ids": {}}]}]}))
    r = offline_checks(ev)
    rep = r["replays"][0]
    assert rep["sdk_outcome"]["raised"] == "BadRequestError" and rep["body_validates_against_sdk_type"] is False
    assert rep["sdk_outcome"]["human_message_extractable"] == "Text cannot be empty"
    assert r["protocol"]["stt_boolean_query_encoding"]["lowercase_true_false"] is True
    assert r["protocol"]["sse_iterator_items"]["yielded"] == []


def test_doc_examples_offline_reproduce_silent_failure_and_nameerror(tmp_path):
    from smallest_qa.doc_examples import canned, run_example

    r = run_example("tts_quickstart_requests.py", mode="offline", api_key="sk_test_doc", workdir=tmp_path / "a",
                    canned_responses={"api": canned(401, b'{"error":"unauthorized"}', "application/json")})
    assert r.exit_code == 0 and r.files[0]["starts_as"] == "json-text" and "Saved output.wav" in r.stdout
    assert r.calls[0]["timeout"] == "None"
    r2 = run_example("stt_transcribe_page_example.py", mode="offline", api_key="sk_test_doc", workdir=tmp_path / "b",
                     canned_responses={}, input_files={"call.wav": b"RIFF"})
    assert r2.exit_code == 1 and "NameError" in r2.stderr_tail and r2.calls == []
    with pytest.raises(ValueError):
        run_example("tts_quickstart_requests.py", mode="live", api_key="x", workdir=tmp_path / "c")
    r3 = run_example("tts_quickstart_requests.py", mode="offline", api_key="sk_test_doc", workdir=tmp_path / "d",
                     canned_responses={})  # nothing canned -> shim refuses, never touches the network
    assert r3.exit_code != 0 and r3.calls == []
