"""Cumulative, persistent request budget (append-only ledger).

Every outbound API request (HTTP or WebSocket connection) is written to the ledger
*before* it is sent, so a crash or timeout mid-request still counts. The cap is
cumulative across all runs and phases. Retries are never automatic; any re-run is a
new ledger entry.

Ledger schema
-------------
v1 (Phase 1, seq 1-28): seq, run_id, case_id, method, path, utc, ist
v2 (Phase 2+): v1 fields + schema=2, phase, batch, protocol ("http"|"ws"),
               est_tts_chars, est_stt_seconds
Entries without a ``phase`` field are Phase 1. Existing lines are never rewritten.
The ``utc``/``ist`` stamp is the *reservation* time, which precedes the pacing delay
(up to inter_request_delay_s) before the request is actually sent; the send time is
recorded in each run's results.json.
"""

from __future__ import annotations

import json
from pathlib import Path

from .timeutil import stamp_pair

# Rough public list prices (smallest.ai/pricing, voice-agent layer figures, fetched 2026-11-22).
TTS_USD_PER_MIN = 0.09
STT_USD_PER_MIN = 0.009
CHARS_PER_SECOND = 14.0  # rough speaking rate used only to convert characters into audio minutes


def estimate_usd(tts_chars: float, stt_seconds: float) -> float:
    return tts_chars / CHARS_PER_SECOND / 60 * TTS_USD_PER_MIN + stt_seconds / 60 * STT_USD_PER_MIN


class BudgetExceeded(RuntimeError):
    pass


class RequestLedger:
    def __init__(self, path: Path, max_requests: int, phase_caps: dict[int, int] | None = None,
                 phase_usd_caps: dict[int, float] | None = None):
        self.path = path
        self.max_requests = max_requests
        self.phase_caps = phase_caps or {}
        self.phase_usd_caps = phase_usd_caps or {}

    def entries(self) -> list[dict]:
        if not self.path.is_file():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines if line.strip()]

    @staticmethod
    def phase_of(entry: dict) -> int:
        return int(entry.get("phase", 1))

    @property
    def used(self) -> int:
        return len(self.entries())

    @property
    def remaining(self) -> int:
        return max(0, self.max_requests - self.used)

    def phase_used(self, phase: int) -> int:
        return sum(1 for e in self.entries() if self.phase_of(e) == phase)

    def phase_remaining(self, phase: int) -> int:
        cap = self.phase_caps.get(phase)
        overall = self.remaining
        return overall if cap is None else max(0, min(overall, cap - self.phase_used(phase)))

    def phase_est_usd(self, phase: int) -> float:
        return sum(estimate_usd(e.get("est_tts_chars", 0), e.get("est_stt_seconds", 0))
                   for e in self.entries() if self.phase_of(e) == phase)

    def reserve(self, *, run_id: str, case_id: str, method: str, path: str, phase: int = 1, batch: str = "",
                protocol: str = "http", est_tts_chars: int = 0, est_stt_seconds: float = 0.0) -> int:
        """Record an intended request; raise if it would exceed any cap."""
        entries = self.entries()
        used = len(entries)
        if used >= self.max_requests:
            raise BudgetExceeded(
                f"Cumulative request cap reached ({used}/{self.max_requests}); refusing {case_id} {method} {path}"
            )
        cap = self.phase_caps.get(phase)
        phase_used = sum(1 for e in entries if self.phase_of(e) == phase)
        if cap is not None and phase_used >= cap:
            raise BudgetExceeded(f"Phase {phase} request cap reached ({phase_used}/{cap}); refusing {case_id}")
        usd_cap = self.phase_usd_caps.get(phase)
        if usd_cap is not None:
            spent = sum(estimate_usd(e.get("est_tts_chars", 0), e.get("est_stt_seconds", 0))
                        for e in entries if self.phase_of(e) == phase)
            if spent + estimate_usd(est_tts_chars, est_stt_seconds) > usd_cap:
                raise BudgetExceeded(f"Phase {phase} estimated spend cap ${usd_cap:.2f} would be exceeded "
                                     f"(${spent:.3f} so far); refusing {case_id}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        seq = used + 1
        entry: dict = {"seq": seq, "run_id": run_id, "case_id": case_id, "method": method, "path": path,
                       **stamp_pair()}
        if phase != 1:  # keep v1 line format byte-compatible for Phase 1 tooling and tests
            entry.update({"schema": 2, "phase": phase, "batch": batch, "protocol": protocol,
                          "est_tts_chars": est_tts_chars, "est_stt_seconds": round(est_stt_seconds, 2)})
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return seq
