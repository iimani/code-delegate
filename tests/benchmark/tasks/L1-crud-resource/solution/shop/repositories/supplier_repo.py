from typing import List, Optional

from shop.models import Supplier
from shop.repositories.base import Repository
from shop.util.dates import from_iso, to_iso


def _row_to_supplier(row) -> Supplier:
    return Supplier(id=row["id"], name=row["name"], email=row["email"], country=row["country"],
                    created_at=from_iso(row["created_at"]))


class SupplierRepository(Repository):
    def add(self, supplier: Supplier) -> None:
        self._exec("INSERT INTO suppliers (id, name, email, country, created_at) VALUES (?, ?, ?, ?, ?)",
                   (supplier.id, supplier.name, supplier.email, supplier.country, to_iso(supplier.created_at)))

    def get(self, supplier_id: str) -> Optional[Supplier]:
        row = self._one("SELECT * FROM suppliers WHERE id = ?", (supplier_id,))
        return _row_to_supplier(row) if row else None

    def get_by_email(self, email: str) -> Optional[Supplier]:
        row = self._one("SELECT * FROM suppliers WHERE email = ?", (email,))
        return _row_to_supplier(row) if row else None

    def list_all(self) -> List[Supplier]:
        return [_row_to_supplier(r) for r in self._all("SELECT * FROM suppliers ORDER BY name, id")]
