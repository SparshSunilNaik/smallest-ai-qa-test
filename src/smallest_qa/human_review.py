"""Local, offline review of a human clip: audio + reference + STT hypothesis side by side.

- Reads the private STT response saved during the run (evidence/private/<run>/<ID>-stt-response.json).
- Lets the speaker play the audio, correct the reference transcript, and recompute WER/CER locally.
- Makes no network request. A corrected reference does not change the audio, so the upload approval stays
  valid; every correction is versioned (reference_history) and the original evaluation file is never
  overwritten: a new revision file is written instead.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from .human import HUMAN_DIR, PROMPTS_BY_ID, clip_paths, load_clip, set_reference
from .human_eval import evaluate_pair
from .timeutil import stamp_pair
from .wer import align, normalized_tokens

_MARK = {"eq": " ", "sub": "S", "del": "D", "ins": "I"}


def side_by_side(reference: str, hypothesis: str, width: int = 28) -> list[str]:
    ops = align(normalized_tokens(reference), normalized_tokens(hypothesis))
    rows = [f"{'#':>3}  {'op':<2} {'reference':<{width}} {'hypothesis':<{width}}", "-" * (8 + 2 * width)]
    for i, o in enumerate(ops, 1):
        rows.append(f"{i:>3}  {_MARK[o.kind]:<2} {(o.ref or '—'):<{width}} {(o.hyp or '—'):<{width}}")
    return rows


def _summary_line(ev: dict) -> str:
    s, n = ev["strict"], ev["normalized"]
    return (f"strict WER {s['wer']:.3f} (S{s['substitutions']} D{s['deletions']} I{s['insertions']} of "
            f"{s['ref_tokens']}), strict CER {s['cer']:.3f} | normalized WER {n['wer']:.3f} "
            f"(S{n['substitutions']} D{n['deletions']} I{n['insertions']}), normalized CER {n['cer']:.3f} | "
            f"recognition-only WER {ev['recognition_only_wer']:.3f}")


def review(prompt_id: str, run_id: str, evidence_dir: Path, *, ask: Callable[[str], str] = input,
           say: Callable[[str], None] = print, play: Callable[[bytes], None] | None = None,
           root: Path = HUMAN_DIR) -> dict | None:
    meta = load_clip(prompt_id, root)
    resp_path = evidence_dir / "private" / run_id / f"{prompt_id}-stt-response.json"
    if not meta or not resp_path.exists():
        say(f"{prompt_id}: no local clip or no saved STT response for run {run_id}")
        return None
    hyp = json.loads(resp_path.read_text(encoding="utf-8")).get("transcription", "")
    lang = PROMPTS_BY_ID[prompt_id].language
    original_ref = meta["reference_transcript"]
    ref = original_ref
    before = evaluate_pair(ref, hyp, lang)
    if play is None:
        from .audio import wav_pcm16
        from .human import Recorder

        def play(wav: bytes) -> None:
            Recorder().play(wav_pcm16(wav)[0])

    while True:
        say(f"\n=== {prompt_id} ({PROMPTS_BY_ID[prompt_id].category}) - run {run_id} - LOCAL ONLY ===")
        say(f"REFERENCE : {ref}")
        say(f"HYPOTHESIS: {hyp}")
        for row in side_by_side(ref, hyp):
            say(row)
        say(_summary_line(evaluate_pair(ref, hyp, lang)))
        choice = ask("[p] play audio  [e] edit reference  [q] finish: ").strip().lower()
        if choice == "p":
            play(clip_paths(prompt_id, root)[0].read_bytes())
        elif choice == "e":
            new = ask("Type the full corrected reference (Enter keeps the current one): ").strip()
            if new:
                ref = new
        elif choice == "q":
            break
    if ref == original_ref:
        say("Reference unchanged; nothing written.")
        return {"changed": False, "before": before}
    after = evaluate_pair(ref, hyp, lang)
    # Version the correction in the private metadata.
    _, meta_path = clip_paths(prompt_id, root)
    m = json.loads(meta_path.read_text(encoding="utf-8"))
    hist = m.setdefault("reference_history", [])
    hist.append({"replaced": stamp_pair(), "previous": original_ref, "reason": "speaker review against audio"})
    meta_path.write_text(json.dumps(m, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    set_reference(prompt_id, ref, root)
    say("Before: " + _summary_line(before))
    say("After : " + _summary_line(after))
    say("Saved locally. Approval unchanged (audio unchanged). Run `smallest-qa human-eval --run "
        f"{run_id} --revision` to write a new committed summary revision (counts only).")
    return {"changed": True, "before": before, "after": after, "revision": len(hist)}
