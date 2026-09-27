"""Money helpers. Amounts are integer cents everywhere in the code base."""
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import List, Union

Amount = Union[str, int, Decimal]


def to_cents(amount: Amount) -> int:
    """Convert a decimal amount ("12.5", Decimal("3.999"), 7) to integer cents.

    Rounds half up to the nearest cent. Floats are rejected (TypeError) because
    they cannot represent most decimal amounts exactly. Invalid strings raise
    ValueError.
    """
    if isinstance(amount, float):
        raise TypeError("use str or Decimal for money, not float")
    try:
        value = Decimal(str(amount).strip())
    except InvalidOperation:
        raise ValueError(f"not a money amount: {amount!r}") from None
    return int((value * 100).quantize(Decimal("1"), rounding="ROUND_HALF_EVEN"))


def format_cents(cents: int, currency: str = "CHF") -> str:
    """Format cents for display: 1250 -> "CHF 12.50", -5 -> "-CHF 0.05"."""
    sign = "-" if cents < 0 else ""
    whole, frac = divmod(abs(cents), 100)
    return f"{sign}{currency} {whole:,}.{frac:02d}".replace(",", "'")


def percent_of(cents: int, percent: Union[int, Decimal, str]) -> int:
    """``percent`` % of ``cents``, rounded half up to a whole cent."""
    value = Decimal(cents) * Decimal(str(percent)) / Decimal(100)
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def split_evenly(cents: int, parts: int) -> List[int]:
    """Split ``cents`` into ``parts`` integer amounts that sum to ``cents``.

    The first ``cents % parts`` parts get one extra cent. ``parts`` must be > 0.
    """
    if parts <= 0:
        raise ValueError("parts must be positive")
    base, remainder = divmod(cents, parts)
    return [base + 1 if i < remainder else base for i in range(parts)]
