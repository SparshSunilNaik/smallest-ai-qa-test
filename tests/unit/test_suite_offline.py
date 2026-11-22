"""End-to-end harness tests against the in-process fake of the documented contract."""

from __future__ import annotations

import json

from fake_api import VALID_KEY, FakeSmallest

from smallest_qa.cases import CASES
from smallest_qa.report import aggregate, load_runs
from smallest_qa.results import CANDIDATE, CONFIRMED_DEFECT, DOC_AMBIGUITY, INCONCLUSIVE, NOT_TESTED, PASSED
from smallest_qa.runner import execute, ledger_for, select_cases


def _run(settings, fixture_wav, fake, ids=None, include_optional=False):
    specs = select_cases(ids, include_optional)
    run_dir = execute(settings, specs, transport=fake.transport(), sleep=lambda s: None, log=lambda *a: None,
                      fixture_provider=lambda: fixture_wav)
    return json.loads((run_dir / "results.json").read_text()), run_dir


def _by_id(payload):
    return {c["case_id"]: c for c in payload["cases"]}


def test_default_selection_fits_budget_with_reproduction_headroom():
    planned = sum(c.planned_requests for c in select_cases(None, False))
    with_optional = sum(c.planned_requests for c in CASES)
    assert planned <= 25 and with_optional <= 28


def test_conformant_fake_yields_expected_classifications(settings, fixture_wav):
    fake = FakeSmallest(reference_text=fixture_wav.reference_text)
    payload, run_dir = _run(settings, fixture_wav, fake, include_optional=True)
    cases = _by_id(payload)
    for cid, case in cases.items():
        failed = [c["name"] for c in case["checks"] if c["passed"] is False]
        expected = DOC_AMBIGUITY if cid == "TTS-07" else PASSED
        assert case["classification"] == expected, (cid, failed, case["notes"])
    # every executed request is in the ledger and the run summary
    assert payload["requests_this_run"] == len(fake.calls) == ledger_for(settings).used
    assert cases["STT-06"]["metrics"]["sample_count"] == 3 and len(cases["STT-06"]["requests"]) == 2
    assert cases["LAT-01"]["metrics"]["ttfb_ms"]["n"] == 5
    assert cases["STR-01"]["metrics"]["first_audio_event_ms"] is not None
    # sanitisation
    text = (run_dir / "results.json").read_text() + (run_dir / "summary.md").read_text()
    assert VALID_KEY not in text
    # private audio kept out of the committed run directory
    assert not list(run_dir.glob("*.wav"))
    assert list((settings.evidence_dir / "private").rglob("TTS-01.wav"))


def test_deviations_become_candidates_not_defects(settings, fixture_wav):
    fake = FakeSmallest(fixture_wav.reference_text, deviations={"accept_empty", "accept_mismatch", "wrong_rate",
                                                                 "no_terminal", "nondeterministic"})
    payload, _ = _run(settings, fixture_wav, fake)
    cases = _by_id(payload)
    for cid in ("TTS-01", "TTS-03", "TTS-07", "STR-01", "STT-06"):
        assert cases[cid]["classification"] == CANDIDATE, cid
    assert cases["AUTH-02"]["classification"] == PASSED


def test_reproduction_across_runs_promotes_to_confirmed(settings, fixture_wav):
    fake = FakeSmallest(fixture_wav.reference_text, deviations={"accept_empty"})
    _run(settings, fixture_wav, fake, ids=["TTS-03"])
    first = aggregate(load_runs(settings.evidence_dir))
    assert first["TTS-03"]["final"] == CANDIDATE
    _run(settings, fixture_wav, fake, ids=["TTS-03"])
    second = aggregate(load_runs(settings.evidence_dir))
    assert second["TTS-03"]["final"] == CONFIRMED_DEFECT and second["TTS-03"]["reproductions"] == 2


def test_exploratory_mismatch_never_confirmed(settings, fixture_wav):
    fake = FakeSmallest(fixture_wav.reference_text, deviations={"nondeterministic"})
    for _ in range(2):
        _run(settings, fixture_wav, fake, ids=["STT-01", "STT-06"])
    agg = aggregate(load_runs(settings.evidence_dir))
    assert agg["STT-06"]["final"] == CANDIDATE  # exploratory checks cannot become confirmed defects


def test_connection_failures_are_inconclusive_and_halt(settings, fixture_wav):
    fake = FakeSmallest(fixture_wav.reference_text, deviations={"transport_error"})
    payload, _ = _run(settings, fixture_wav, fake)
    cases = _by_id(payload)
    assert cases["AUTH-01"]["classification"] == INCONCLUSIVE
    assert payload["halted"] and payload["requests_this_run"] == 2
    assert all(c["classification"] == NOT_TESTED for cid, c in cases.items() if cid not in ("AUTH-01", "AUTH-02"))


def test_budget_exhaustion_skips_cases_without_overspending(settings, fixture_wav):
    small = settings.__class__(**{**settings.__dict__, "max_requests": 4})
    fake = FakeSmallest(fixture_wav.reference_text)
    payload, _ = _run(small, fixture_wav, fake)
    assert ledger_for(small).used == 4 == len(fake.calls)
    assert sum(1 for c in payload["cases"] if c["classification"] == NOT_TESTED) >= 10
