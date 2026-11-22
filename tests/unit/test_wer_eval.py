"""Scoring rules for Batch 3h: strict vs normalized, S/D/I, numeric formatting vs recognition, Hinglish script."""

from __future__ import annotations

from smallest_qa.translit import loose_key, transliterate_word
from smallest_qa.wer import align, canonical_numbers, classify_regions, normalize_text, normalized_tokens, score


def test_strict_counts_case_and_punctuation_normalized_does_not():
    s = score("Hello, World.", "hello world")
    assert s["strict"]["wer"] == 1.0 and s["normalized"]["wer"] == 0.0


def test_normalization_rules_are_explicit():
    assert normalize_text("That’s ₹3,075.40 — OK।") == "that's 3075.40 ok"
    assert normalized_tokens("version 2.3, total 3,075") == ["version", "2.3", "total", "3075"]


def test_alignment_reports_substitution_deletion_insertion():
    ops = align("a b c d".split(), "a x c d e".split())
    assert [o.kind for o in ops] == ["eq", "sub", "eq", "eq", "ins"]
    s = score("a b c d", "a c d")
    assert (s["normalized"]["deletions"], s["normalized"]["wer"]) == (1, 0.25)


def test_numeric_formatting_is_not_a_recognition_error():
    ref = "order 3 1 8 6 total 2,050 rupees and 25 paise by the 18th"
    hyp = "order three one eight six total two thousand fifty rupees and twenty-five paisa by the eighteenth"
    labels = {r["label"] for r in classify_regions(score(ref, hyp)["_ops_normalized"])}
    assert labels == {"numeric_formatting"}
    assert canonical_numbers("two point three") == canonical_numbers("2.3") == [("2.3", "")]
    assert canonical_numbers("₹2,050.25") == canonical_numbers("2050 rupees and 25 paise")


def test_numeric_recognition_error_detected():
    labels = [r["label"] for r in classify_regions(score("pay 450 rupees", "pay 540 rupees")["_ops_normalized"])]
    assert labels == ["numeric_recognition"]


def test_segmentation_and_disfluency_labels():
    seg = classify_regions(score("sometime next week", "some time next week")["_ops_normalized"])
    assert [r["label"] for r in seg] == ["segmentation"]
    dis = classify_regions(score("so um we left", "so we left")["_ops_normalized"])
    assert [r["label"] for r in dis] == ["disfluency_omitted"]


def test_hinglish_transliteration_matches_romanised_reference_without_rewriting():
    pairs = [("मीटिंग", "meeting"), ("कैंसल", "cancel"), ("प्लीज़", "please"), ("ईमेल", "email"), ("न्यू", "new"),
             ("कन्फ़र्म", "confirm"), ("सुबह", "subah")]
    assert all(loose_key(transliterate_word(d)) == loose_key(r) for d, r in pairs)
    assert loose_key(transliterate_word("दिल्ली")) != loose_key("email")  # unrelated words stay different


def test_human_eval_public_output_withholds_unshared_text(tmp_path):
    import json

    from test_human_workflow import FakeRecorder, _script

    from smallest_qa.human import record_session, set_approval
    from smallest_qa.human_eval import evaluate_run

    human = tmp_path / "human"
    record_session(["H1"], recorder=FakeRecorder(), root=human, say=lambda *_: None,
                   ask=_script("", "", "a", "my secret reference words"))
    set_approval("H1", True, root=human)
    ev = tmp_path / "evidence"
    (ev / "runs" / "R").mkdir(parents=True)
    (ev / "private" / "R").mkdir(parents=True)
    (ev / "runs" / "R" / "results.json").write_text(json.dumps({"run_id": "R", "cases": [
        {"case_id": "P2-HUM-01", "metrics": {}, "requests": [{"request_ids": {"x-request-id": "rid"}}]}]}))
    (ev / "private" / "R" / "H1-stt-response.json").write_text(json.dumps({"transcription": "my secret words"}))
    detail, public = evaluate_run(ev, "R", human_root=human)
    blob = json.dumps(public)
    assert "secret" not in blob and public["clips"]["H1"]["normalized"]["deletions"] == 1
    assert detail["clips"]["H1"]["reference"] == "my secret reference words"
