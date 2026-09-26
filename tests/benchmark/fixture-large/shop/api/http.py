"""Framework-free request/response types used by the router and handlers."""
from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class Request:
    method: str
    path: str
    query: Dict[str, str] = field(default_factory=dict)
    body: Dict[str, Any] = field(default_factory=dict)
    params: Dict[str, str] = field(default_factory=dict)  # filled in by the router from the path


@dataclass
class Response:
    status: int
    body: Any
