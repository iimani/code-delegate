from shop.errors import CONFLICT, INVALID, NOT_FOUND, Result, fail, ok
from shop.models import Product
from shop.repositories.inventory_repo import InventoryRepository
from shop.repositories.product_repo import ProductRepository
from shop.services.validation import validate_name, validate_price_cents, validate_sku
from shop.util.ids import new_id
from shop.util.money import Amount, to_cents
from shop.util.text import normalize_whitespace


def _parse_price(price: Amount) -> Result:
    try:
        cents = to_cents(price)
    except (TypeError, ValueError) as e:
        return fail(INVALID, str(e))
    problem = validate_price_cents(cents)
    return fail(INVALID, problem) if problem else ok(cents)


class ProductService:
    def __init__(self, products: ProductRepository, inventory: InventoryRepository) -> None:
        self.products = products
        self.inventory = inventory

    def create(self, sku: str, name: str, price: Amount) -> Result:
        sku = (sku or "").strip().upper()
        name = normalize_whitespace(name or "")
        problem = validate_sku(sku) or validate_name(name)
        if problem:
            return fail(INVALID, problem)
        cents, err = _parse_price(price)
        if err:
            return None, err
        if self.products.get_by_sku(sku):
            return fail(CONFLICT, f"SKU {sku} already exists")
        product = Product(id=new_id("prd"), sku=sku, name=name, price_cents=cents)
        self.products.add(product)
        self.inventory.create(product.id)
        return ok(product)

    def get(self, product_id: str) -> Result:
        product = self.products.get(product_id)
        if product is None:
            return fail(NOT_FOUND, f"no product {product_id}")
        return ok(product)

    def list(self, active_only: bool = False) -> Result:
        return ok(self.products.list_all(active_only=active_only))

    def change_price(self, product_id: str, price: Amount) -> Result:
        product, err = self.get(product_id)
        if err:
            return None, err
        cents, err = _parse_price(price)
        if err:
            return None, err
        self.products.update_price(product_id, cents)
        product.price_cents = cents
        return ok(product)

    def deactivate(self, product_id: str) -> Result:
        product, err = self.get(product_id)
        if err:
            return None, err
        if not product.active:
            return fail(CONFLICT, f"product {product_id} is already inactive")
        self.products.set_active(product_id, False)
        product.active = False
        return ok(product)
