from __future__ import annotations

import math
import statistics


def percentile_nearest_rank(values: list[float], pct: float) -> float:
    """Nearest-rank percentile. With small n this is a coarse estimate (n=5 -> p95 == max)."""
    if not values:
        raise ValueError("no samples")
    ordered = sorted(values)
    rank = max(1, math.ceil(pct / 100 * len(ordered)))
    return ordered[rank - 1]


def summarize(values: list[float]) -> dict[str, float | int]:
    vals = [v for v in values if v is not None]
    if not vals:
        return {"n": 0}
    return {
        "n": len(vals),
        "min": round(min(vals), 1),
        "median": round(statistics.median(vals), 1),
        "p95_nearest_rank": round(percentile_nearest_rank(vals, 95), 1),
        "max": round(max(vals), 1),
    }
