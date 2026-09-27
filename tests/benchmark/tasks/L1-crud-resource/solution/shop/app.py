"""Composition root: builds repositories, services and the router on one connection."""
import sqlite3
from typing import Any, Dict, Optional
from urllib.parse import parse_qsl, urlsplit

from shop import db
from shop.api import customers as customer_routes
from shop.api import orders as order_routes
from shop.api import products as product_routes
from shop.api import suppliers as supplier_routes
from shop.api.http import Request, Response
from shop.api.router import Router
from shop.repositories.customer_repo import CustomerRepository
from shop.repositories.inventory_repo import InventoryRepository
from shop.repositories.order_repo import OrderRepository
from shop.repositories.product_repo import ProductRepository
from shop.repositories.supplier_repo import SupplierRepository
from shop.services.customer_service import CustomerService
from shop.services.inventory_service import InventoryService
from shop.services.order_service import OrderService
from shop.services.product_service import ProductService
from shop.services.supplier_service import SupplierService
from shop.util.clock import Clock, utc_now


class App:
    def __init__(self, conn: sqlite3.Connection, clock: Clock = utc_now) -> None:
        self.conn = conn
        self.clock = clock
        self.customer_repo = CustomerRepository(conn)
        self.product_repo = ProductRepository(conn)
        self.inventory_repo = InventoryRepository(conn)
        self.order_repo = OrderRepository(conn)
        self.supplier_repo = SupplierRepository(conn)

        self.customer_service = CustomerService(self.customer_repo, clock)
        self.supplier_service = SupplierService(self.supplier_repo, clock)
        self.product_service = ProductService(self.product_repo, self.inventory_repo)
        self.inventory_service = InventoryService(self.inventory_repo, self.product_repo)
        self.order_service = OrderService(self.order_repo, self.customer_repo, self.product_repo,
                                          self.inventory_service, clock)

        self.router = Router()
        customer_routes.register(self.router, self)
        product_routes.register(self.router, self)
        order_routes.register(self.router, self)
        supplier_routes.register(self.router, self)

    def handle(self, method: str, path: str, body: Optional[Dict[str, Any]] = None) -> Response:
        """Dispatch a request; ``path`` may include a query string."""
        url = urlsplit(path)
        return self.router.dispatch(Request(method, url.path, dict(parse_qsl(url.query, keep_blank_values=True)), body or {}))


def build_app(path: str = ":memory:", clock: Clock = utc_now) -> App:
    return App(db.connect(path), clock)
