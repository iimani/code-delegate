Add a type-safe in-memory cache with per-key TTL, plus its tests. Two new files.

`app/cache.py` must define `TTLCache`, generic over the stored value type (`TTLCache(Generic[V])` with a `TypeVar` `V`, so `TTLCache[int]` is valid). Keys are strings.

- `TTLCache(default_ttl, clock=time.monotonic)` — `default_ttl` is in seconds and must be > 0 (else `ValueError`). `clock` is a zero-argument callable returning the current time in seconds; all expiry decisions must use it (never call `time` directly elsewhere), so tests can inject a fake clock.
- `set(key, value, ttl=None) -> None` — stores the value; `ttl` overrides `default_ttl` for this key and must be > 0 when given (else `ValueError`). Setting an existing key replaces its value and restarts its TTL.
- `get(key, default=None) -> Optional[V]` — returns the value, or `default` if the key is missing or expired. An entry set at time `t` with TTL `n` is expired when `clock() >= t + n`.
- `delete(key) -> bool` — removes the key; returns `True` only if a non-expired entry was removed.
- `len(cache)` counts only non-expired entries; `key in cache` is `True` only for non-expired entries.
- Annotate all public methods with type hints that use `V`.

`tests/test_cache.py` must use `unittest` and cover get/set, overwrite, delete, and TTL expiry (both default and per-key TTL) using an injected fake clock — no `time.sleep`.

Python 3.9+, standard library only. Do not modify any other file. The full suite must pass: `python3 -m unittest discover -s tests -t .`
