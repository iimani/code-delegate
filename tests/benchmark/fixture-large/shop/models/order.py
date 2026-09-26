from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

PLACED = "placed"
CANCELLED = "cancelled"


@dataclass
class OrderLine:
    product_id: str
    quantity: int
    unit_price_cents: int

    @property
    def total_cents(self) -> int:
        return self.quantity * self.unit_price_cents


@dataclass
class Order:
    id: str
    customer_id: str
    status: str
    created_at: datetime
    subtotal_cents: int
    discount_cents: int
    vat_cents: int
    total_cents: int
    discount_code: Optional[str] = None
    lines: List[OrderLine] = field(default_factory=list)
