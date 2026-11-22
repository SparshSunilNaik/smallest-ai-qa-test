from __future__ import annotations

import pytest
from fake_api import make_wav

from smallest_qa.audio import AudioFormatError, looks_like_mp3, parse_wav, pcm16_rms_dbfs
from smallest_qa.budget import BudgetExceeded, RequestLedger
from smallest_qa.config import Settings, _parse_dotenv
from smallest_qa.redact import REDACTED, redact_headers, redact_text, safe_excerpt
from smallest_qa.sse import SSEParser
from smallest_qa.stats import percentile_nearest_rank, summarize
from smallest_qa.textsim import normalize, word_error_rate


# --- redaction -------------------------------------------------------------------
def test_redacts_known_secret_and_key_patterns():
    s = "key sk_abcdef123456 token wat_zzzzzz999 Bearer abc.def-ghi123 custom-SECRET-42"
    out = redact_text(s, secrets=("custom-SECRET-42",))
    assert "sk_abcdef123456" not in out and "wat_zzzzzz999" not in out and "abc.def-ghi123" not in out
    assert "custom-SECRET-42" not in out and out.count(REDACTED) == 4


def test_redact_headers_masks_authorization_case_insensitively():
    h = redact_headers({"authorization": "Bearer sk_live_xyz123456", "X-Request-Id": "r1"})
    assert h == {"authorization": REDACTED, "X-Request-Id": "r1"}


def test_safe_excerpt_omits_audio_payloads():
    out = safe_excerpt('event: audio\ndata: {"audio":"QUJDREVGR0g=","done":false}\n\n')
    assert "QUJDREVGR0g=" not in out and "<12 base64 chars omitted>" in out and '"done":false' in out


def test_safe_excerpt_bounds_length():
    assert len(safe_excerpt(b"x" * 5000, limit=100)) < 130


# --- config ----------------------------------------------------------------------
def test_dotenv_parser_and_key_never_in_repr(tmp_path):
    env = tmp_path / ".env"
    env.write_text('# c\nexport SMALLEST_API_KEY="sk_secret_value_1"\nOTHER=1\n')
    vals = _parse_dotenv(env)
    assert vals["SMALLEST_API_KEY"] == "sk_secret_value_1"
    s = Settings(api_key=vals["SMALLEST_API_KEY"])
    assert "sk_secret_value_1" not in repr(s)
    assert "sk_secret_value_1" not in s.key_fingerprint


# --- budget ----------------------------------------------------------------------
def test_ledger_is_cumulative_across_instances(tmp_path):
    path = tmp_path / "ledger.jsonl"
    a = RequestLedger(path, max_requests=3)
    a.reserve(run_id="r1", case_id="X", method="GET", path="/a")
    a.reserve(run_id="r1", case_id="X", method="GET", path="/a")
    b = RequestLedger(path, max_requests=3)  # a later run sees earlier usage
    assert b.used == 2 and b.remaining == 1
    b.reserve(run_id="r2", case_id="Y", method="GET", path="/b")
    with pytest.raises(BudgetExceeded):
        b.reserve(run_id="r2", case_id="Y", method="GET", path="/b")
    assert b.used == 3


# --- SSE -------------------------------------------------------------------------
def test_sse_parser_handles_split_chunks_crlf_and_comments():
    p = SSEParser()
    stream = b': keepalive\r\nevent: audio\r\ndata: {"a":1}\r\n\r\nevent: audio\ndata: {"done": true}\n\n'
    events = []
    for i in range(0, len(stream), 7):
        events += p.feed(stream[i : i + 7], t_ms=float(i))
    assert [e.event for e in events] == ["audio", "audio"]
    assert events[1].data == '{"done": true}' and p.pending_bytes == 0


def test_sse_flush_dispatches_unterminated_event():
    p = SSEParser()
    assert p.feed(b"data: tail") == []
    out = p.flush(1.0)
    assert len(out) == 1 and out[0].data == "tail" and len(p.events) == 1


def test_sse_multiline_data_joined():
    p = SSEParser()
    (ev,) = p.feed("data: one\ndata: two\n\n")
    assert ev.data == "one\ntwo" and ev.event == "message"


# --- audio -----------------------------------------------------------------------
def test_parse_wav_reads_rate_and_duration():
    info = parse_wav(make_wav(24000, 1.0))
    assert info.sample_rate == 24000 and info.channels == 1 and info.bits_per_sample == 16
    assert abs(info.duration_s - 1.0) < 0.01


def test_parse_wav_streaming_sentinel_size_uses_actual_bytes():
    wav = bytearray(make_wav(16000, 0.5))
    data_pos = wav.find(b"data")
    wav[data_pos + 4 : data_pos + 8] = b"\xff\xff\xff\xff"
    info = parse_wav(bytes(wav))
    assert info.data_bytes == len(wav) - (data_pos + 8)


@pytest.mark.parametrize("blob", [b"", b"ID3", b"{\"error\":1}", b"RIFF\x00\x00\x00\x00WAVX"])
def test_parse_wav_rejects_non_wav(blob):
    with pytest.raises(AudioFormatError):
        parse_wav(blob)


def test_mp3_detection_and_silence_level():
    assert looks_like_mp3(b"ID3\x04") and looks_like_mp3(b"\xff\xfb\x90") and not looks_like_mp3(b"RIFF")
    assert pcm16_rms_dbfs(b"\x00\x00" * 100) == float("-inf")
    assert pcm16_rms_dbfs(make_wav(16000, 0.2)[44:]) > -30


# --- stats / text ---------------------------------------------------------------
def test_percentiles_nearest_rank_small_n():
    vals = [100.0, 120.0, 110.0, 300.0, 105.0]
    assert percentile_nearest_rank(vals, 95) == 300.0  # n=5 -> p95 is the max
    assert summarize(vals)["median"] == 110.0 and summarize([])["n"] == 0


def test_wer_and_normalisation():
    assert normalize("Hello, World!") == ["hello", "world"]
    assert word_error_rate("the quick brown fox", "The quick, brown fox.") == 0.0
    assert word_error_rate("a b c d", "a x c") == 0.5


def test_normalize_keeps_devanagari_vowel_signs_and_drops_danda():
    from smallest_qa.textsim import char_error_rate, key_token_hits

    assert normalize("आज मौसम अच्छा है।") == ["आज", "मौसम", "अच्छा", "है"]
    assert char_error_rate("मौसम", "मसम") > 0  # a dropped matra must count as an error
    assert key_token_hits("Balance is $1,250.75", [["1250", "twelve fifty"], ["dollars", "$"]])["hit"] == 1


def test_scrub_paths_hides_home_and_tmp():
    import os

    from smallest_qa.redact import scrub_paths

    home = os.path.expanduser("~")
    out = scrub_paths(f'File "{home}/x.py" and /private/var/folders/ab/cd/T/tmp1/y.py')
    assert home not in out and "/var/folders" not in out and "~/x.py" in out
