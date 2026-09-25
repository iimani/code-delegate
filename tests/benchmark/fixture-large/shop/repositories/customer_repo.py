from typing import List, Optional

from shop.models import Customer
from shop.repositories.base import Repository
from shop.util.dates import from_iso, to_iso


def _row_to_customer(row) -> Customer:
    return Customer(id=row["id"], name=row["name"], email=row["email"],
                    created_at=from_iso(row["created_at"]))


class CustomerRepository(Repository):
    def add(self, customer: Customer) -> None:
        self._exec("INSERT INTO customers (id, name, email, created_at) VALUES (?, ?, ?, ?)",
                   (customer.id, customer.name, customer.email, to_iso(customer.created_at)))

    def get(self, customer_id: str) -> Optional[Customer]:
        row = self._one("SELECT * FROM customers WHERE id = ?", (customer_id,))
        return _row_to_customer(row) if row else None

    def get_by_email(self, email: str) -> Optional[Customer]:
        row = self._one("SELECT * FROM customers WHERE email = ?", (email,))
        return _row_to_customer(row) if row else None

    def list_all(self) -> List[Customer]:
        return [_row_to_customer(r) for r in self._all("SELECT * FROM customers ORDER BY created_at, name, id")]
