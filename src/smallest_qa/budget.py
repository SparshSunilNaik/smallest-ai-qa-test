"""Cumulative, persistent request budget.

Every outbound API request is written to the ledger *before* it is sent, so a crash
or timeout mid-request still counts. The cap is cumulative across all runs of the
investigation, not per test or per run. Retries are never automatic; any re-run is
a new ledger entry.
"""

from __future__ import annotations

import json
from pathlib import Path

from .timeutil import stamp_pair


class BudgetExceeded(RuntimeError):
    pass


class RequestLedger:
    def __init__(self, path: Path, max_requests: int):
        self.path = path
        self.max_requests = max_requests

    def entries(self) -> list[dict]:
        if not self.path.is_file():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines if line.strip()]

    @property
    def used(self) -> int:
        return len(self.entries())

    @property
    def remaining(self) -> int:
        return max(0, self.max_requests - self.used)

    def reserve(self, *, run_id: str, case_id: str, method: str, path: str) -> int:
        """Record an intended request; raise if it would exceed the cumulative cap."""
        used = self.used
        if used >= self.max_requests:
            raise BudgetExceeded(
                f"Cumulative request cap reached ({used}/{self.max_requests}); refusing {case_id} {method} {path}"
            )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        seq = used + 1
        entry = {"seq": seq, "run_id": run_id, "case_id": case_id, "method": method, "path": path, **stamp_pair()}
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return seq
