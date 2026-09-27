from datetime import date, timedelta
from typing import Dict

from shop.models.order import PLACED
from shop.reports.base import Report


def sales_report(app, start: date, end: date) -> Report:
    """One row per calendar day from ``start`` to ``end`` inclusive, days without orders included.

    Columns: date (YYYY-MM-DD), orders (count of placed orders), revenue_cents (sum of totals).
    """
    orders, err = app.order_service.list_between(start, end)
    if err:
        raise ValueError(err.message)
    per_day: Dict[date, list] = {}
    for order in orders:
        if order.status == PLACED:
            per_day.setdefault(order.created_at.date(), []).append(order)
    report = Report(f"Sales {start.isoformat()} to {end.isoformat()}", ["date", "orders", "revenue_cents"])
    day = start
    while day <= end:
        todays = per_day.get(day, [])
        report.rows.append({"date": day.isoformat(), "orders": len(todays),
                            "revenue_cents": sum(o.total_cents for o in todays)})
        day += timedelta(days=1)
    return report
