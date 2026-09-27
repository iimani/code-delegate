Add CSV and JSON export for every report in `shop/reports/`, reachable from the CLI and the API. Read how reports, the CLI and the API currently work first.

- **`shop/reports/export.py`**:
  - `to_csv(report) -> str`: written with `csv.writer` using the default dialect (so lines end in `\r\n`). First row is `report.columns`, then one row per report row with values in column order.
  - `to_json(report) -> str`: `json.dumps({"title": ..., "columns": [...], "rows": [...]}, indent=2)` where each row is an object whose keys follow the column order. Numbers stay numbers.
  - `FORMATS`: dict mapping `"text"`, `"csv"`, `"json"` to `render_text`, `to_csv`, `to_json`.
  - `export(report, fmt) -> str`: dispatches on `FORMATS`; an unknown format raises `ValueError`.
- **CLI**: `report NAME` gains `--format {text,csv,json}` (default `text`) and writes the exported string unchanged to stdout.
- **API**: `GET /reports/{name}` with query parameters `format` (default `json`) and, for the sales report, `from` and `to` (YYYY-MM-DD). Success is 200 with body `{"name": <name>, "format": <format>, "content": <exported string>}`. Unknown report name → 404; unknown format, missing/invalid dates, or a reversed date range → 400. Use the existing error body shape (`{"error": ..., "message": ...}`) with error `"not_found"` or `"invalid"`.
- **Tests**: `tests/test_export.py` covering both formats, the CLI flag and the endpoint.

Python 3.9+, standard library only. Don't change existing behaviour. The full suite must pass: `python3 -m unittest discover -s tests -t .`
