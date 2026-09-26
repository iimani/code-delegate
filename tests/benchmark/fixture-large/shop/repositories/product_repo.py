from typing import List, Optional

from shop.models import Product
from shop.repositories.base import Repository


def _row_to_product(row) -> Product:
    return Product(id=row["id"], sku=row["sku"], name=row["name"],
                   price_cents=row["price_cents"], active=bool(row["active"]))


class ProductRepository(Repository):
    def add(self, product: Product) -> None:
        self._exec("INSERT INTO products (id, sku, name, price_cents, active) VALUES (?, ?, ?, ?, ?)",
                   (product.id, product.sku, product.name, product.price_cents, int(product.active)))

    def get(self, product_id: str) -> Optional[Product]:
        row = self._one("SELECT * FROM products WHERE id = ?", (product_id,))
        return _row_to_product(row) if row else None

    def get_by_sku(self, sku: str) -> Optional[Product]:
        row = self._one("SELECT * FROM products WHERE sku = ?", (sku,))
        return _row_to_product(row) if row else None

    def list_all(self, active_only: bool = False) -> List[Product]:
        sql = "SELECT * FROM products"
        if active_only:
            sql += " WHERE active = 1"
        return [_row_to_product(r) for r in self._all(sql + " ORDER BY sku")]

    def update_price(self, product_id: str, price_cents: int) -> None:
        self._exec("UPDATE products SET price_cents = ? WHERE id = ?", (price_cents, product_id))

    def set_active(self, product_id: str, active: bool) -> None:
        self._exec("UPDATE products SET active = ? WHERE id = ?", (int(active), product_id))
