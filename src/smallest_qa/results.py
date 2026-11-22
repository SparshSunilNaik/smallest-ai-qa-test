from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .client import Exchange

# Classification vocabulary (fixed by the investigation brief).
PASSED = "Passed"
CONFIRMED_DEFECT = "Confirmed defect"
CANDIDATE = "Candidate finding requiring reproduction"
EXPECTED = "Expected behavior"
DOC_AMBIGUITY = "Documentation ambiguity"
INCONCLUSIVE = "Inconclusive"
NOT_TESTED = "Not tested"
CLASSIFICATIONS = [PASSED, CONFIRMED_DEFECT, CANDIDATE, EXPECTED, DOC_AMBIGUITY, INCONCLUSIVE, NOT_TESTED]

# Requirement provenance for each assertion.
DOCUMENTED = "documented"  # stated in official docs -> deviations can become defects
QUALITY = "quality"  # reasonable quality expectation, not stated in docs -> observation only
EXPLORATORY = "exploratory"  # open question / measurement; no pass/fail claim against docs


@dataclass
class Check:
    name: str
    passed: bool | None  # None = could not be evaluated
    expected: str
    actual: str
    requirement: str = DOCUMENTED
    doc_ref: str | None = None


@dataclass
class CaseResult:
    case_id: str
    title: str
    area: str
    expected_behavior: str
    doc_refs: list[str]
    classification: str = NOT_TESTED
    checks: list[Check] = field(default_factory=list)
    exchanges: list[Exchange] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def check(self, name: str, passed: bool | None, expected: str, actual: Any, requirement: str = DOCUMENTED,
              doc_ref: str | None = None) -> bool | None:
        self.checks.append(Check(name, passed, expected, str(actual), requirement, doc_ref))
        return passed

    @property
    def failed_checks(self) -> list[Check]:
        return [c for c in self.checks if c.passed is False]

    def to_dict(self, secrets: tuple[str, ...]) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "title": self.title,
            "area": self.area,
            "expected_behavior": self.expected_behavior,
            "doc_refs": self.doc_refs,
            "classification": self.classification,
            "checks": [asdict(c) for c in self.checks],
            "metrics": self.metrics,
            "notes": self.notes,
            "requests": [ex.to_evidence(secrets) for ex in self.exchanges],
        }


def auto_classify(result: CaseResult) -> str:
    """Conservative default. Never yields CONFIRMED_DEFECT (that needs cross-run reproduction)."""
    if not result.exchanges:
        return NOT_TESTED
    for ex in result.exchanges:
        if ex.error or ex.status is None or ex.status >= 500 or ex.status == 429:
            return INCONCLUSIVE
    if any(c.passed is None and c.requirement == DOCUMENTED for c in result.checks) and not result.failed_checks:
        return INCONCLUSIVE
    return PASSED if not result.failed_checks else CANDIDATE
