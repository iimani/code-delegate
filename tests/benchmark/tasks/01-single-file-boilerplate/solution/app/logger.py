import json
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

LEVELS = ("debug", "info", "warn", "error")


def log(level: str, message: str, context: Optional[Dict[str, Any]] = None) -> None:
    if level not in LEVELS:
        raise ValueError(f"invalid level {level!r}; expected one of {LEVELS}")
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "message": message,
        "context": context if context is not None else {},
    }
    sys.stdout.write(json.dumps(record) + "\n")
