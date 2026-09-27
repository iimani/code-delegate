"""Input checks shared by services. Each returns an error message, or None when valid."""
import re
from typing import Optional

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
SKU_RE = re.compile(r"^[A-Z0-9][A-Z0-9-]{2,19}$")
MAX_NAME_LENGTH = 100
MAX_QUANTITY = 10_000


def validate_name(name: str) -> Optional[str]:
    if not name or not name.strip():
        return "name is required"
    if len(name) > MAX_NAME_LENGTH:
        return f"name must be at most {MAX_NAME_LENGTH} characters"
    return None


def validate_email(email: str) -> Optional[str]:
    if not email or not EMAIL_RE.match(email):
        return f"invalid email address: {email!r}"
    return None


def validate_sku(sku: str) -> Optional[str]:
    if not sku or not SKU_RE.match(sku):
        return f"invalid SKU {sku!r}: 3-20 characters, A-Z, 0-9 and '-', not starting with '-'"
    return None


def validate_price_cents(cents: int) -> Optional[str]:
    if cents <= 0:
        return "price must be greater than zero"
    return None


def validate_quantity(quantity: int) -> Optional[str]:
    if not isinstance(quantity, int) or isinstance(quantity, bool):
        return "quantity must be a whole number"
    if quantity < 1 or quantity > MAX_QUANTITY:
        return f"quantity must be between 1 and {MAX_QUANTITY}"
    return None
