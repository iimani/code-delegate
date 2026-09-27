import re


def normalize_whitespace(value: str) -> str:
    """Trim and collapse internal runs of whitespace to one space."""
    return re.sub(r"\s+", " ", value).strip()


def truncate(value: str, width: int) -> str:
    """Cut ``value`` to ``width`` characters, ending with "…" when shortened."""
    if width < 1:
        raise ValueError("width must be at least 1")
    return value if len(value) <= width else value[: width - 1] + "…"
