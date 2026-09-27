from shop.errors import ConflictError, NotFoundError, ValidationError
from shop.models import InventoryLevel
from shop.repositories.inventory_repo import InventoryRepository
from shop.repositories.product_repo import ProductRepository
from shop.services.validation import validate_quantity


def _check_quantity(quantity: int) -> None:
    problem = validate_quantity(quantity)
    if problem:
        raise ValidationError(problem)


class InventoryService:
    """Stock levels. ``reserved`` counts units promised to placed orders."""

    def __init__(self, inventory: InventoryRepository, products: ProductRepository) -> None:
        self.inventory = inventory
        self.products = products

    def level(self, product_id: str) -> InventoryLevel:
        level = self.inventory.get(product_id)
        if level is None:
            raise NotFoundError(f"no product {product_id}")
        return level

    def receive(self, product_id: str, quantity: int) -> InventoryLevel:
        _check_quantity(quantity)
        self.level(product_id)
        self.inventory.add_on_hand(product_id, quantity)
        return self.level(product_id)

    def reserve(self, product_id: str, quantity: int) -> InventoryLevel:
        _check_quantity(quantity)
        level = self.level(product_id)
        if level.available < quantity:
            raise ConflictError(f"only {level.available} of {product_id} available, {quantity} requested")
        self.inventory.add_reserved(product_id, quantity)
        return self.level(product_id)

    def release(self, product_id: str, quantity: int) -> InventoryLevel:
        _check_quantity(quantity)
        level = self.level(product_id)
        if quantity > level.reserved:
            raise ValidationError(f"cannot release {quantity}; only {level.reserved} reserved")
        self.inventory.add_reserved(product_id, -quantity)
        return self.level(product_id)
