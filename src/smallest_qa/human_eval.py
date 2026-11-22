"""Offline evaluation of Batch 3h STT results (no API requests).

Inputs: the run's committed results.json (synthetic transcripts are committed; human ones are not), the private
per-clip STT responses in evidence/private/<run>/, and local clip metadata (reference transcripts).
Outputs:
- evidence/private/<run>/human-eval-detail.json  (git-ignored: tokens, alignments, transcripts)
- evidence/offline/human-eval-<run>.json         (committed: counts and rates only for human clips, unless the
                                                  speaker approved with --share-transcript)
"""

from __future__ import annotations

import json
from pathlib import Path

from .translit import is_devanagari, loose_key, transliterate_word
from .wer import align, classify_regions, counts, normalized_tokens, score

RECOGNITION_LABELS = ("word_recognition", "numeric_recognition")


def _region_summary(regions: list[dict]) -> dict:
    out: dict = {}
    for r in regions:
        o = out.setdefault(r["label"], {"regions": 0, "error_ops": 0})
        o["regions"] += 1
        o["error_ops"] += len(r["ops"])
    return out


def evaluate_pair(reference: str, hypothesis: str, language: str) -> dict:
    sc = score(reference, hypothesis)
    ops = sc.pop("_ops_normalized")
    regions = classify_regions(ops)
    n = sc["normalized"]["ref_tokens"]
    rec_ops = sum(len(r["ops"]) for r in regions if r["label"] in RECOGNITION_LABELS)
    result = {**sc, "regions": regions, "region_summary": _region_summary(regions),
              "recognition_only_wer": round(rec_ops / n, 4) if n else 0.0}
    hyp_tokens = normalized_tokens(hypothesis)
    result["script"] = {"hyp_tokens": len(hyp_tokens),
                        "devanagari_tokens": sum(is_devanagari(t) for t in hyp_tokens),
                        "latin_tokens": sum(t.isascii() and t.isalpha() for t in hyp_tokens)}
    if language == "hi" and result["script"]["devanagari_tokens"]:
        ref_keys = [loose_key(t) for t in normalized_tokens(reference)]
        hyp_keys = [loose_key(transliterate_word(t)) if is_devanagari(t) else loose_key(t) for t in hyp_tokens]
        t_ops = align(ref_keys, hyp_keys)
        result["transliteration_aware"] = {
            **counts(t_ops, len(ref_keys)),
            "method": "Devanagari->Latin approximate transliteration + loose phonetic key (translit.py); "
                      "analysis aid only; the original transcript is unchanged",
        }
    return result


def _sanitize(ev: dict) -> dict:
    out = {k: v for k, v in ev.items() if k not in ("regions",)}
    return out


def evaluate_run(evidence_dir: Path, run_id: str, human_root: Path | None = None) -> tuple[dict, dict]:
    from .human import PROMPTS_BY_ID, load_clip

    run = json.loads((evidence_dir / "runs" / run_id / "results.json").read_text(encoding="utf-8"))
    private = evidence_dir / "private" / run_id
    detail, public = {"run_id": run_id, "clips": {}}, {"run_id": run_id, "clips": {}, "synthetic_baseline": {}}
    controls = {}
    for case in run["cases"]:
        cid = case["case_id"]
        if cid.startswith("P2-HUM-"):
            pid = "H" + cid[-1]
            meta = load_clip(pid, human_root) if human_root else load_clip(pid)
            resp_path = private / f"{pid}-stt-response.json"
            if not meta or not resp_path.exists():
                public["clips"][pid] = {"status": "not evaluated (missing local clip or private response)"}
                continue
            resp = json.loads(resp_path.read_text(encoding="utf-8"))
            hyp, ref = resp.get("transcription", ""), meta["reference_transcript"]
            p = PROMPTS_BY_ID[pid]
            ev = evaluate_pair(ref, hyp, p.language)
            share = bool(meta.get("share_transcript_in_evidence"))
            detail["clips"][pid] = {"reference": ref, "hypothesis": hyp, **ev}
            pub = {"case_id": cid, "category": p.category, "model": p.model, "language": p.language,
                   "duration_s": meta["duration_s"], "reference_edited": meta["reference_edited"],
                   "request_id": (case["requests"][0]["request_ids"].get("x-request-id")
                                  if case["requests"] else None),
                   "transcript_shared": share, **_sanitize(ev)}
            if share:
                pub.update({"reference": ref, "hypothesis": hyp, "regions": ev["regions"]})
            public["clips"][pid] = pub
            if pid == "H4":
                controls["H4_ref"] = ref
        elif cid.startswith("P2-STT-") and case["metrics"].get("reference"):
            m = case["metrics"]
            ev = evaluate_pair(m["reference"], m["transcription"], m.get("fixture", {}).get("recipe", {})
                               .get("language", "en"))
            public["synthetic_baseline"][cid] = {
                "fixture": m.get("fixture", {}).get("fixture_id"), "strict": ev["strict"],
                "normalized": ev["normalized"], "recognition_only_wer": ev["recognition_only_wer"],
                "region_summary": ev["region_summary"]}
            if cid == "P2-STT-11":
                controls["unrelated_hindi_hyp"] = m["transcription"]
    if "H4_ref" in controls and "unrelated_hindi_hyp" in controls:
        neg = evaluate_pair(controls["H4_ref"], controls["unrelated_hindi_hyp"], "hi")
        public["negative_control"] = {
            "description": "H4 reference vs an unrelated Hindi transcript (P2-STT-11): transliteration-aware WER "
                           "should be high if loose matching is not producing false matches",
            "transliteration_aware_wer": neg.get("transliteration_aware", {}).get("wer"),
            "hits": neg.get("transliteration_aware", {}).get("hits")}
    return detail, public
