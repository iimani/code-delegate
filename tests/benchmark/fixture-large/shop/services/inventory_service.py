from shop.errors import CONFLICT, INVALID, NOT_FOUND, Result, fail, ok
from shop.repositories.inventory_repo import InventoryRepository
from shop.repositories.product_repo import ProductRepository
from shop.services.validation import validate_quantity


class InventoryService:
    """Stock levels. ``reserved`` counts units promised to placed orders."""

    def __init__(self, inventory: InventoryRepository, products: ProductRepository) -> None:
        self.inventory = inventory
        self.products = products

    def level(self, product_id: str) -> Result:
        level = self.inventory.get(product_id)
        if level is None:
            return fail(NOT_FOUND, f"no product {product_id}")
        return ok(level)

    def receive(self, product_id: str, quantity: int) -> Result:
        problem = validate_quantity(quantity)
        if problem:
            return fail(INVALID, problem)
        _, err = self.level(product_id)
        if err:
            return None, err
        self.inventory.add_on_hand(product_id, quantity)
        return self.level(product_id)

    def reserve(self, product_id: str, quantity: int) -> Result:
        problem = validate_quantity(quantity)
        if problem:
            return fail(INVALID, problem)
        level, err = self.level(product_id)
        if err:
            return None, err
        if level.available < quantity:
            return fail(CONFLICT, f"only {level.available} of {product_id} available, {quantity} requested")
        self.inventory.add_reserved(product_id, quantity)
        return self.level(product_id)

    def release(self, product_id: str, quantity: int) -> Result:
        problem = validate_quantity(quantity)
        if problem:
            return fail(INVALID, problem)
        level, err = self.level(product_id)
        if err:
            return None, err
        if quantity > level.reserved:
            return fail(INVALID, f"cannot release {quantity}; only {level.reserved} reserved")
        self.inventory.add_reserved(product_id, -quantity)
        return self.level(product_id)
