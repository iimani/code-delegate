from datetime import datetime
from typing import List, Optional

from shop.models import Order, OrderLine
from shop.repositories.base import Repository
from shop.util.dates import from_iso, to_iso


class OrderRepository(Repository):
    def add(self, order: Order) -> None:
        self.conn.execute(
            "INSERT INTO orders (id, customer_id, status, created_at, subtotal_cents, discount_cents, "
            "vat_cents, total_cents, discount_code) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (order.id, order.customer_id, order.status, to_iso(order.created_at), order.subtotal_cents,
             order.discount_cents, order.vat_cents, order.total_cents, order.discount_code))
        for position, line in enumerate(order.lines):
            self.conn.execute(
                "INSERT INTO order_lines (order_id, position, product_id, quantity, unit_price_cents) "
                "VALUES (?, ?, ?, ?, ?)",
                (order.id, position, line.product_id, line.quantity, line.unit_price_cents))
        self.conn.commit()

    def set_status(self, order_id: str, status: str) -> None:
        self._exec("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))

    def get(self, order_id: str) -> Optional[Order]:
        row = self._one("SELECT * FROM orders WHERE id = ?", (order_id,))
        return self._load(row) if row else None

    def list_for_customer(self, customer_id: str) -> List[Order]:
        rows = self._all("SELECT * FROM orders WHERE customer_id = ? ORDER BY created_at, id", (customer_id,))
        return [self._load(r) for r in rows]

    def list_between(self, start: datetime, end: datetime) -> List[Order]:
        """Orders created in [start, end], both inclusive, oldest first."""
        rows = self._all(
            "SELECT * FROM orders WHERE created_at >= ? AND created_at <= ? ORDER BY created_at, id",
            (to_iso(start), to_iso(end)))
        return [self._load(r) for r in rows]

    def _load(self, row) -> Order:
        lines = [OrderLine(product_id=l["product_id"], quantity=l["quantity"],
                           unit_price_cents=l["unit_price_cents"])
                 for l in self._all("SELECT * FROM order_lines WHERE order_id = ? ORDER BY position", (row["id"],))]
        return Order(id=row["id"], customer_id=row["customer_id"], status=row["status"],
                     created_at=from_iso(row["created_at"]), subtotal_cents=row["subtotal_cents"],
                     discount_cents=row["discount_cents"], vat_cents=row["vat_cents"],
                     total_cents=row["total_cents"], discount_code=row["discount_code"], lines=lines)
