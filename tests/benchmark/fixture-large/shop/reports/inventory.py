from shop.reports.base import Report

LOW_STOCK_THRESHOLD = 5


def inventory_report(app) -> Report:
    """Stock per active product, ordered by SKU. low_stock is "yes" when available < LOW_STOCK_THRESHOLD."""
    report = Report("Inventory", ["sku", "name", "on_hand", "reserved", "available", "low_stock"])
    products, _ = app.product_service.list(active_only=True)
    for product in products:
        level, _ = app.inventory_service.level(product.id)
        report.rows.append({
            "sku": product.sku, "name": product.name, "on_hand": level.on_hand, "reserved": level.reserved,
            "available": level.available, "low_stock": "yes" if level.available < LOW_STOCK_THRESHOLD else "no",
        })
    return report
