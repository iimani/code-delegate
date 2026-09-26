from typing import List, Optional

from shop.models import InventoryLevel
from shop.repositories.base import Repository


def _row_to_level(row) -> InventoryLevel:
    return InventoryLevel(product_id=row["product_id"], on_hand=row["on_hand"], reserved=row["reserved"])


class InventoryRepository(Repository):
    def create(self, product_id: str) -> None:
        self._exec("INSERT INTO inventory (product_id, on_hand, reserved) VALUES (?, 0, 0)", (product_id,))

    def get(self, product_id: str) -> Optional[InventoryLevel]:
        row = self._one("SELECT * FROM inventory WHERE product_id = ?", (product_id,))
        return _row_to_level(row) if row else None

    def list_all(self) -> List[InventoryLevel]:
        return [_row_to_level(r) for r in self._all("SELECT * FROM inventory ORDER BY product_id")]

    def add_on_hand(self, product_id: str, quantity: int) -> None:
        self._exec("UPDATE inventory SET on_hand = on_hand + ? WHERE product_id = ?", (quantity, product_id))

    def add_reserved(self, product_id: str, quantity: int) -> None:
        """Change the reserved count by ``quantity`` (negative to release)."""
        self._exec("UPDATE inventory SET reserved = reserved + ? WHERE product_id = ?", (quantity, product_id))
