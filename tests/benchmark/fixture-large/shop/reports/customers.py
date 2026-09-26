from shop.models.order import PLACED
from shop.reports.base import Report


def top_customers_report(app, limit: int = 10) -> Report:
    """Customers by revenue from placed orders, highest first, then by name. Customers without orders excluded."""
    customers, _ = app.customer_service.list()
    rows = []
    for customer in customers:
        orders, _ = app.order_service.list_for_customer(customer.id)
        placed = [o for o in orders if o.status == PLACED]
        if placed:
            rows.append({"name": customer.name, "email": customer.email, "orders": len(placed),
                         "revenue_cents": sum(o.total_cents for o in placed)})
    rows.sort(key=lambda r: (-r["revenue_cents"], r["name"]))
    return Report("Top customers", ["name", "email", "orders", "revenue_cents"], rows[:limit])
