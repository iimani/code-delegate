from typing import Iterable, Tuple

LineItem = Tuple[str, int, float]  # (sku, quantity, unit_price)


def order_subtotal(items: Iterable[LineItem]) -> float:
    """Sum of quantity * unit_price over all line items, rounded to cents."""
    return round(sum(qty * price for _sku, qty, price in items), 2)


def apply_discount(amount: float, percent: float) -> float:
    if not 0 <= percent <= 100:
        raise ValueError("percent must be between 0 and 100")
    return round(amount * (100 - percent) / 100, 2)
