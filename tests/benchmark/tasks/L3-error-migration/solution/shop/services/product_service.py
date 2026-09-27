from typing import List

from shop.errors import ConflictError, NotFoundError, ValidationError
from shop.models import Product
from shop.repositories.inventory_repo import InventoryRepository
from shop.repositories.product_repo import ProductRepository
from shop.services.validation import validate_name, validate_price_cents, validate_sku
from shop.util.ids import new_id
from shop.util.money import Amount, to_cents
from shop.util.text import normalize_whitespace


def _parse_price(price: Amount) -> int:
    try:
        cents = to_cents(price)
    except (TypeError, ValueError) as e:
        raise ValidationError(str(e)) from None
    problem = validate_price_cents(cents)
    if problem:
        raise ValidationError(problem)
    return cents


class ProductService:
    def __init__(self, products: ProductRepository, inventory: InventoryRepository) -> None:
        self.products = products
        self.inventory = inventory

    def create(self, sku: str, name: str, price: Amount) -> Product:
        sku = (sku or "").strip().upper()
        name = normalize_whitespace(name or "")
        problem = validate_sku(sku) or validate_name(name)
        if problem:
            raise ValidationError(problem)
        cents = _parse_price(price)
        if self.products.get_by_sku(sku):
            raise ConflictError(f"SKU {sku} already exists")
        product = Product(id=new_id("prd"), sku=sku, name=name, price_cents=cents)
        self.products.add(product)
        self.inventory.create(product.id)
        return product

    def get(self, product_id: str) -> Product:
        product = self.products.get(product_id)
        if product is None:
            raise NotFoundError(f"no product {product_id}")
        return product

    def list(self, active_only: bool = False) -> List[Product]:
        return self.products.list_all(active_only=active_only)

    def change_price(self, product_id: str, price: Amount) -> Product:
        product = self.get(product_id)
        cents = _parse_price(price)
        self.products.update_price(product_id, cents)
        product.price_cents = cents
        return product

    def deactivate(self, product_id: str) -> Product:
        product = self.get(product_id)
        if not product.active:
            raise ConflictError(f"product {product_id} is already inactive")
        self.products.set_active(product_id, False)
        product.active = False
        return product
