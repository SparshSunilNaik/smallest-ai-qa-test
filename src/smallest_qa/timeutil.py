from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def stamp_pair(moment: datetime | None = None) -> dict[str, str]:
    moment = moment or now_utc()
    return {
        "utc": moment.astimezone(timezone.utc).isoformat(timespec="milliseconds"),
        "ist": moment.astimezone(IST).isoformat(timespec="milliseconds"),
    }


def run_id(moment: datetime | None = None) -> str:
    moment = moment or now_utc()
    return moment.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
