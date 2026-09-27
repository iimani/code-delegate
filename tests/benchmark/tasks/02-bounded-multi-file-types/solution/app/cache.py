import time
from typing import Callable, Dict, Generic, Optional, Tuple, TypeVar

V = TypeVar("V")


class TTLCache(Generic[V]):
    def __init__(self, default_ttl: float, clock: Callable[[], float] = time.monotonic) -> None:
        if default_ttl <= 0:
            raise ValueError("default_ttl must be > 0")
        self._default_ttl = default_ttl
        self._clock = clock
        self._entries: Dict[str, Tuple[V, float]] = {}

    def _live(self, key: str) -> bool:
        entry = self._entries.get(key)
        if entry is None:
            return False
        if self._clock() >= entry[1]:
            del self._entries[key]
            return False
        return True

    def set(self, key: str, value: V, ttl: Optional[float] = None) -> None:
        if ttl is not None and ttl <= 0:
            raise ValueError("ttl must be > 0")
        self._entries[key] = (value, self._clock() + (ttl if ttl is not None else self._default_ttl))

    def get(self, key: str, default: Optional[V] = None) -> Optional[V]:
        return self._entries[key][0] if self._live(key) else default

    def delete(self, key: str) -> bool:
        if self._live(key):
            del self._entries[key]
            return True
        return False

    def __len__(self) -> int:
        return sum(1 for key in list(self._entries) if self._live(key))

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and self._live(key)
