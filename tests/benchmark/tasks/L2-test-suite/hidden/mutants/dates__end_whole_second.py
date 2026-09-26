"""Date and time helpers. All datetimes are timezone-naive UTC."""
from datetime import date, datetime, time, timedelta
from typing import Tuple


def parse_date(value: str) -> date:
    """Parse "YYYY-MM-DD"; raises ValueError for anything else."""
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except (ValueError, AttributeError):
        raise ValueError(f"expected a date as YYYY-MM-DD, got {value!r}") from None


def day_bounds(day: date) -> Tuple[datetime, datetime]:
    """First and last representable instant of ``day`` (both inclusive)."""
    start = datetime.combine(day, time.min)
    return start, datetime.combine(day, time(23, 59, 59))


def to_iso(moment: datetime) -> str:
    """Storage format for timestamps: ISO 8601 with a "T" separator, seconds precision."""
    return moment.replace(microsecond=0).isoformat()


def from_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


def add_business_days(day: date, count: int) -> date:
    """Move ``count`` business days (Mon–Fri) forward, or backward if negative."""
    step = 1 if count >= 0 else -1
    remaining = abs(count)
    current = day
    while remaining:
        current += timedelta(days=step)
        if current.weekday() < 5:
            remaining -= 1
    return current


def days_between(start: date, end: date) -> int:
    """Number of calendar days from ``start`` to ``end`` inclusive; 0 if end < start."""
    return max((end - start).days + 1, 0)
