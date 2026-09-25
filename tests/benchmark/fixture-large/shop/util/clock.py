from datetime import datetime
from typing import Callable

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.utcnow().replace(microsecond=0)


class FixedClock:
    """Test clock: returns ``now`` until changed with ``set``."""

    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def set(self, now: datetime) -> None:
        self.now = now
