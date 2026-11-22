"""Human recording workflow: consent gates, local storage, approval binding, evidence privacy. No mic, no network."""

from __future__ import annotations

import json
import subprocess

from fake_api_p2 import FakeP2, tone_pcm

from smallest_qa.cases_p2 import P2_BY_ID
from smallest_qa.config import REPO_ROOT, Settings
from smallest_qa.human import (PROMPTS_BY_ID, load_approved_audio, load_clip, record_session, set_approval,
                               summary_rows)
from smallest_qa.results import NOT_TESTED, PASSED
from smallest_qa.runner import execute, ledger_for


class FakeRecorder:
    def __init__(self):
        self.recordings = 0
        self.played = 0

    def device_name(self):
        return "Test Mic"

    def record(self, wait_for_stop, max_seconds):
        wait_for_stop()
        self.recordings += 1
        return tone_pcm(f"take{self.recordings}", 16000, 2.0)

    def play(self, pcm):
        self.played += 1


def _script(*answers):
    it = iter(answers)
    return lambda prompt="": next(it)


def test_accept_with_edited_reference_saves_locally_unapproved(tmp_path):
    rec = FakeRecorder()
    out = record_session(["H1"], recorder=rec, root=tmp_path, say=lambda *_: None,
                         ask=_script("", "", "p", "a", "Hi, I want to move my appointment to next week."))
    assert len(out) == 1 and rec.played == 1
    m = load_clip("H1", tmp_path)
    assert m["reference_edited"] is True and m["approved_for_upload"] is False and not m["approval_valid"]
    assert (tmp_path / "H1.wav").stat().st_mode & 0o777 == 0o600
    assert load_approved_audio("H1", tmp_path) is None  # cannot be sent yet


def test_discard_and_skip_write_nothing(tmp_path):
    record_session(["H1", "H2"], recorder=FakeRecorder(), root=tmp_path, say=lambda *_: None,
                   ask=_script("", "", "d", "s"))
    assert not list(tmp_path.glob("*"))


def test_rerecord_then_accept_and_spontaneous_requires_transcript(tmp_path):
    rec = FakeRecorder()
    record_session(["H5"], recorder=rec, root=tmp_path, say=lambda *_: None,
                   ask=_script("", "", "r", "", "", "a", "", "I watched a cricket match and made dinner."))
    m = load_clip("H5", tmp_path)
    assert rec.recordings == 2 and m["reference_transcript"].startswith("I watched")


def test_approval_is_bound_to_audio_hash(tmp_path):
    record_session(["H3"], recorder=FakeRecorder(), root=tmp_path, say=lambda *_: None,
                   ask=_script("", "", "a", ""))
    set_approval("H3", True, root=tmp_path)
    assert load_approved_audio("H3", tmp_path)
    (tmp_path / "H3.wav").write_bytes((tmp_path / "H3.wav").read_bytes()[:-2] + b"\x01\x00")  # re-recorded/edited
    assert load_approved_audio("H3", tmp_path) is None
    assert summary_rows(tmp_path)[2]["stale_approval"] is True


def _run_human(settings, fixture_wav, tmp_path, fake):
    s = Settings(**{**settings.__dict__, "max_requests": 128})
    spec = P2_BY_ID["P2-HUM-01"]
    import smallest_qa.cases_p2 as c2

    orig = c2.Context.__init__

    def init(self, *a, **k):
        orig(self, *a, **k)
        self.state["human_dir"] = tmp_path / "human"

    c2.Context.__init__ = init
    try:
        run_dir = execute(s, [spec], transport=fake.transport(), sleep=lambda x: None, log=lambda *a: None,
                          fixture_provider=lambda: fixture_wav, phase=2, batch="3h", doc_example_mode="skip")
    finally:
        c2.Context.__init__ = orig
    return json.loads((run_dir / "results.json").read_text())["cases"][0], ledger_for(s)


def test_unapproved_clip_is_never_sent(settings, fixture_wav, tmp_path):
    root = tmp_path / "human"
    record_session(["H1"], recorder=FakeRecorder(), root=root, say=lambda *_: None, ask=_script("", "", "a", ""))
    fake = FakeP2()
    case, led = _run_human(settings, fixture_wav, tmp_path, fake)
    assert case["classification"] == NOT_TESTED and case["requests"] == [] and fake.calls == []
    assert led.phase_used(2) == 0


def test_approved_clip_sent_once_and_transcript_withheld_without_opt_in(settings, fixture_wav, tmp_path):
    root = tmp_path / "human"
    record_session(["H1"], recorder=FakeRecorder(), root=root, say=lambda *_: None, ask=_script("", "", "a", ""))
    set_approval("H1", True, root=root)
    fake = FakeP2()
    wav = (root / "H1.wav").read_bytes()
    fake.register(wav, PROMPTS_BY_ID["H1"].reference)
    case, led = _run_human(settings, fixture_wav, tmp_path, fake)
    assert len(fake.calls) == 1 and led.phase_used(2) == 1 and case["classification"] == PASSED
    blob = json.dumps(case)
    assert "reschedule" not in blob and case["metrics"]["transcripts_shared_in_evidence"] is False
    assert case["metrics"]["wer"] == 0.0


def test_human_audio_directory_is_git_ignored():
    r = subprocess.run(["git", "check-ignore", "-q", "fixtures/audio/human/H1.wav"], cwd=REPO_ROOT)
    assert r.returncode == 0
