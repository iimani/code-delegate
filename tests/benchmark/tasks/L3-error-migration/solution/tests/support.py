"""Shared test setup: an in-memory app with a fixed clock and a few seeded records."""
from datetime import datetime

from shop.app import build_app
from shop.util.clock import FixedClock

START = datetime(2026, 3, 2, 10, 0, 0)


def make_app(now: datetime = START):
    clock = FixedClock(now)
    return build_app(":memory:", clock), clock


def seed(app):
    """Two customers, three products (stock 20, 3 and 0)."""
    alice = app.customer_service.create("Alice Adams", "alice@example.com")
    bob = app.customer_service.create("Bob Brown", "bob@example.com")
    pen = app.product_service.create("PEN-001", "Blue pen", "2.50")
    pad = app.product_service.create("PAD-001", "Paper pad", "4.90")
    ink = app.product_service.create("INK-001", "Ink bottle", "12.00")
    app.inventory_service.receive(pen.id, 20)
    app.inventory_service.receive(pad.id, 3)
    return {"alice": alice, "bob": bob, "pen": pen, "pad": pad, "ink": ink}
