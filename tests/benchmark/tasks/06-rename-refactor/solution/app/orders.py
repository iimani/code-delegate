from typing import List

from app.pricing import LineItem, apply_discount, order_subtotal


class Order:
    def __init__(self, items: List[LineItem], discount_percent: float = 0) -> None:
        self.items = list(items)
        self.discount_percent = discount_percent

    def total(self) -> float:
        return apply_discount(order_subtotal(self.items), self.discount_percent)

    def summary(self) -> str:
        return f"{len(self.items)} items, total {self.total():.2f}"
