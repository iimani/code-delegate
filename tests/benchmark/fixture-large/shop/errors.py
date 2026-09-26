"""Error convention for the service layer.

Service methods return a ``(value, error)`` tuple instead of raising:

    customer, err = service.create(name, email)
    if err:
        ...  # err.kind is one of the KIND_* constants, err.message is human readable

Use ``ok(value)`` and ``fail(kind, message)`` to build the tuples.
"""
from dataclasses import dataclass
from typing import Any, Optional, Tuple

NOT_FOUND = "not_found"
INVALID = "invalid"
CONFLICT = "conflict"

KINDS = (NOT_FOUND, INVALID, CONFLICT)


@dataclass(frozen=True)
class Error:
    kind: str
    message: str


Result = Tuple[Any, Optional[Error]]


def ok(value: Any) -> Result:
    return value, None


def fail(kind: str, message: str) -> Result:
    if kind not in KINDS:
        raise ValueError(f"unknown error kind: {kind}")
    return None, Error(kind, message)
