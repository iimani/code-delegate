from datetime import date
from typing import List, Optional, Sequence, Tuple

from shop.errors import NotFoundError, ServiceError, ValidationError
from shop.models import Order, OrderLine
from shop.models.order import PLACED
from shop.repositories.customer_repo import CustomerRepository
from shop.repositories.order_repo import OrderRepository
from shop.repositories.product_repo import ProductRepository
from shop.services.inventory_service import InventoryService
from shop.services.pricing import normalize_code, price_order
from shop.services.validation import validate_quantity
from shop.util.clock import Clock
from shop.util.dates import day_bounds
from shop.util.ids import new_id

Item = Tuple[str, int]  # (product_id, quantity)


class OrderService:
    def __init__(self, orders: OrderRepository, customers: CustomerRepository, products: ProductRepository,
                 inventory: InventoryService, clock: Clock) -> None:
        self.orders = orders
        self.customers = customers
        self.products = products
        self.inventory = inventory
        self.clock = clock

    def place(self, customer_id: str, items: Sequence[Item], discount_code: Optional[str] = None) -> Order:
        """Validate, price and reserve stock for a new order. Nothing is reserved if any step fails."""
        if self.customers.get(customer_id) is None:
            raise NotFoundError(f"no customer {customer_id}")
        if not items:
            raise ValidationError("an order needs at least one item")
        seen = set()
        lines: List[OrderLine] = []
        for product_id, quantity in items:
            if product_id in seen:
                raise ValidationError(f"product {product_id} listed more than once")
            seen.add(product_id)
            problem = validate_quantity(quantity)
            if problem:
                raise ValidationError(problem)
            product = self.products.get(product_id)
            if product is None:
                raise NotFoundError(f"no product {product_id}")
            if not product.active:
                raise ValidationError(f"product {product.sku} is not for sale")
            lines.append(OrderLine(product_id, quantity, product.price_cents))
        try:
            price = price_order(lines, discount_code)
        except ValueError as e:
            raise ValidationError(str(e)) from None

        reserved: List[OrderLine] = []
        try:
            for line in lines:
                self.inventory.reserve(line.product_id, line.quantity)
                reserved.append(line)
        except ServiceError:
            for done in reserved:
                self.inventory.release(done.product_id, done.quantity)
            raise

        order = Order(id=new_id("ord"), customer_id=customer_id, status=PLACED, created_at=self.clock(),
                      subtotal_cents=price.subtotal_cents, discount_cents=price.discount_cents,
                      vat_cents=price.vat_cents, total_cents=price.total_cents,
                      discount_code=normalize_code(discount_code), lines=lines)
        self.orders.add(order)
        return order

    def get(self, order_id: str) -> Order:
        order = self.orders.get(order_id)
        if order is None:
            raise NotFoundError(f"no order {order_id}")
        return order

    def list_for_customer(self, customer_id: str) -> List[Order]:
        if self.customers.get(customer_id) is None:
            raise NotFoundError(f"no customer {customer_id}")
        return self.orders.list_for_customer(customer_id)

    def list_between(self, start: date, end: date) -> List[Order]:
        """Orders placed from the first instant of ``start`` to the last instant of ``end``."""
        if end < start:
            raise ValidationError("end date is before start date")
        return self.orders.list_between(day_bounds(start)[0], day_bounds(end)[1])
