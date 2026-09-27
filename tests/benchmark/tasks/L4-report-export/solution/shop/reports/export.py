import csv
import io
import json

from shop.reports.base import Report, render_text


def to_csv(report: Report) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(report.columns)
    for row in report.rows:
        writer.writerow([row[c] for c in report.columns])
    return buf.getvalue()


def to_json(report: Report) -> str:
    return json.dumps({"title": report.title, "columns": list(report.columns),
                       "rows": [{c: row[c] for c in report.columns} for row in report.rows]}, indent=2)


FORMATS = {"text": render_text, "csv": to_csv, "json": to_json}


def export(report: Report, fmt: str) -> str:
    if fmt not in FORMATS:
        raise ValueError(f"unknown format {fmt!r}; choose from {', '.join(sorted(FORMATS))}")
    return FORMATS[fmt](report)
