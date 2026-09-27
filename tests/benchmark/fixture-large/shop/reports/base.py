from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class Report:
    """A titled table. Every row has exactly the keys in ``columns``."""

    title: str
    columns: List[str]
    rows: List[Dict[str, Any]] = field(default_factory=list)


def render_text(report: Report) -> str:
    """Plain-text table: title, header, dashed rule, one line per row; columns left-aligned."""
    cells = [[str(c) for c in report.columns]] + [[str(row[c]) for c in report.columns] for row in report.rows]
    widths = [max(len(r[i]) for r in cells) for i in range(len(report.columns))]
    lines = [report.title, "  ".join(h.ljust(w) for h, w in zip(cells[0], widths)).rstrip(),
             "  ".join("-" * w for w in widths)]
    lines += ["  ".join(v.ljust(w) for v, w in zip(r, widths)).rstrip() for r in cells[1:]]
    return "\n".join(lines) + "\n"
