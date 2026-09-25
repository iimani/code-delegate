from datetime import date
from typing import List, Optional, Sequence, Tuple

from shop.errors import CONFLICT, INVALID, NOT_FOUND, Result, fail, ok
from shop.models import Order, OrderLine
from shop.models.order import CANCELLED, PLACED
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

    def place(self, customer_id: str, items: Sequence[Item], discount_code: Optional[str] = None) -> Result:
        """Validate, price and reserve stock for a new order. Nothing is reserved if any step fails."""
        if self.customers.get(customer_id) is None:
            return fail(NOT_FOUND, f"no customer {customer_id}")
        if not items:
            return fail(INVALID, "an order needs at least one item")
        seen = set()
        lines: List[OrderLine] = []
        for product_id, quantity in items:
            if product_id in seen:
                return fail(INVALID, f"product {product_id} listed more than once")
            seen.add(product_id)
            problem = validate_quantity(quantity)
            if problem:
                return fail(INVALID, problem)
            product = self.products.get(product_id)
            if product is None:
                return fail(NOT_FOUND, f"no product {product_id}")
            if not product.active:
                return fail(INVALID, f"product {product.sku} is not for sale")
            lines.append(OrderLine(product_id, quantity, product.price_cents))
        try:
            price = price_order(lines, discount_code)
        except ValueError as e:
            return fail(INVALID, str(e))

        reserved: List[OrderLine] = []
        for line in lines:
            _, err = self.inventory.reserve(line.product_id, line.quantity)
            if err:
                for done in reserved:
                    self.inventory.release(done.product_id, done.quantity)
                return None, err
            reserved.append(line)

        order = Order(id=new_id("ord"), customer_id=customer_id, status=PLACED, created_at=self.clock(),
                      subtotal_cents=price.subtotal_cents, discount_cents=price.discount_cents,
                      vat_cents=price.vat_cents, total_cents=price.total_cents,
                      discount_code=normalize_code(discount_code), lines=lines)
        self.orders.add(order)
        return ok(order)

    def get(self, order_id: str) -> Result:
        order = self.orders.get(order_id)
        if order is None:
            return fail(NOT_FOUND, f"no order {order_id}")
        return ok(order)

    def cancel(self, order_id: str) -> Result:
        """Cancel a placed order and release its reserved stock."""
        order, err = self.get(order_id)
        if err:
            return None, err
        if order.status != PLACED:
            return fail(CONFLICT, f"order {order_id} is {order.status}, only placed orders can be cancelled")
        for line in order.lines:
            self.inventory.release(line.product_id, line.quantity)
        self.orders.set_status(order_id, CANCELLED)
        order.status = CANCELLED
        return ok(order)

    def list_for_customer(self, customer_id: str) -> Result:
        if self.customers.get(customer_id) is None:
            return fail(NOT_FOUND, f"no customer {customer_id}")
        return ok(self.orders.list_for_customer(customer_id))

    def list_between(self, start: date, end: date) -> Result:
        """Orders placed from the first instant of ``start`` to the last instant of ``end``."""
        if end < start:
            return fail(INVALID, "end date is before start date")
        return ok(self.orders.list_between(day_bounds(start)[0], day_bounds(end)[1]))
