"""Human listening pack. Machines verify integrity; only people judge how speech sounds.

Per run with audio to judge:
- evidence/private/<run>/listening.html  (git-ignored; local <audio> players, shuffled order, no case hints)
- reports/listening/<run>-sheet.csv     (committed; blank rating columns for listeners to fill)
"""

from __future__ import annotations

import csv
import html
import random
from pathlib import Path

COLUMNS = ["clip_id", "case_id", "text", "listen_for", "listener", "date", "playback_device",
           "intelligible_1to5", "matches_text_yes_no", "mispronounced_words", "naturalness_1to5",
           "artifacts_none_click_cutoff_noise_robotic_other", "notes"]


def write_listening_pack(run_id: str, queue: list[dict], private_dir: Path, reports_dir: Path) -> tuple[Path, Path]:
    order = list(queue)
    random.Random(run_id).shuffle(order)  # deterministic per run; hides the case ordering from listeners
    rows = [{"clip_id": f"L{i + 1:02d}", **item} for i, item in enumerate(order)]
    private_dir.mkdir(parents=True, exist_ok=True)
    page = ["<!doctype html><meta charset='utf-8'><title>Listening pack</title>",
            "<style>body{font:16px system-ui;max-width:760px;margin:24px auto;padding:0 16px}"
            "section{border-bottom:1px solid #ccc;padding:12px 0}</style>",
            f"<h1>Listening pack {html.escape(run_id)}</h1>",
            "<p>Use headphones. For each clip, read the text, listen once, then fill the matching row in "
            f"<code>reports/listening/{html.escape(run_id)}-sheet.csv</code>. Judge only what you hear.</p>"]
    for r in rows:
        page.append(f"<section><h2>{r['clip_id']}</h2><p>{html.escape(r['text'])}</p>"
                    f"<p><em>Listen for:</em> {html.escape(r.get('focus') or 'general intelligibility')}</p>"
                    f"<audio controls preload='none' src='{html.escape(r['clip'])}'></audio></section>")
    html_path = private_dir / "listening.html"
    html_path.write_text("\n".join(page), encoding="utf-8")
    reports_dir.mkdir(parents=True, exist_ok=True)
    csv_path = reports_dir / f"{run_id}-sheet.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({"clip_id": r["clip_id"], "case_id": r["case_id"], "text": r["text"],
                        "listen_for": r.get("focus") or "general intelligibility"})
    return html_path, csv_path


def load_ratings(reports_dir: Path) -> list[dict]:
    """Only rows a human actually filled in (listener + at least one rating) count."""
    out = []
    for p in sorted(reports_dir.glob("*-sheet.csv")):
        with p.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if row.get("listener") and (row.get("intelligible_1to5") or row.get("matches_text_yes_no")):
                    out.append({**row, "sheet": p.name})
    return out
