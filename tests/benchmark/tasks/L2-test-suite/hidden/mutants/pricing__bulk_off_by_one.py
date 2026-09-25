"""Order pricing: subtotal, discount codes and VAT, all in integer cents."""
from decimal import Decimal
from typing import Iterable, NamedTuple, Optional

from shop.models import OrderLine
from shop.util.money import percent_of

VAT_PERCENT = Decimal("8.1")

# code -> percent off the subtotal
DISCOUNT_CODES = {"WELCOME10": 10, "SPRING15": 15}
# Bulk discount: BULK5 gives 5 % but only for orders of at least BULK_MIN_ITEMS items in total.
BULK_CODE = "BULK5"
BULK_PERCENT = 5
BULK_MIN_ITEMS = 10


class PriceBreakdown(NamedTuple):
    subtotal_cents: int
    discount_cents: int
    vat_cents: int
    total_cents: int


def normalize_code(code: Optional[str]) -> Optional[str]:
    """Codes are case-insensitive and ignore surrounding spaces; blank means no code."""
    if code is None or not code.strip():
        return None
    return code.strip().upper()


def discount_percent(code: Optional[str], total_items: int) -> int:
    """Percent off for ``code``. Raises ValueError for unknown codes or an unmet bulk minimum."""
    code = normalize_code(code)
    if code is None:
        return 0
    if code == BULK_CODE:
        if total_items <= BULK_MIN_ITEMS:
            raise ValueError(f"{BULK_CODE} needs at least {BULK_MIN_ITEMS} items")
        return BULK_PERCENT
    if code not in DISCOUNT_CODES:
        raise ValueError(f"unknown discount code: {code}")
    return DISCOUNT_CODES[code]


def price_order(lines: Iterable[OrderLine], discount_code: Optional[str] = None) -> PriceBreakdown:
    """Subtotal of all lines, minus the discount, plus VAT on the discounted amount.

    Each step rounds half up to whole cents (see shop.util.money.percent_of).
    """
    lines = list(lines)
    subtotal = sum(line.total_cents for line in lines)
    percent = discount_percent(discount_code, sum(line.quantity for line in lines))
    discount = percent_of(subtotal, percent)
    vat = percent_of(subtotal - discount, VAT_PERCENT)
    return PriceBreakdown(subtotal, discount, vat, subtotal - discount + vat)
