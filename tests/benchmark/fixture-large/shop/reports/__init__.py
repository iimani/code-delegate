"""Tabular reports. ``REPORTS`` maps a report name to its builder."""
from shop.reports.customers import top_customers_report
from shop.reports.inventory import inventory_report
from shop.reports.sales import sales_report

REPORTS = {
    "sales": sales_report,
    "inventory": inventory_report,
    "customers": top_customers_report,
}
