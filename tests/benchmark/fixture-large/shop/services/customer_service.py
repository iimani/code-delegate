from typing import List

from shop.errors import CONFLICT, INVALID, NOT_FOUND, Result, fail, ok
from shop.models import Customer
from shop.repositories.customer_repo import CustomerRepository
from shop.services.validation import validate_email, validate_name
from shop.util.clock import Clock
from shop.util.ids import new_id
from shop.util.text import normalize_whitespace


class CustomerService:
    def __init__(self, customers: CustomerRepository, clock: Clock) -> None:
        self.customers = customers
        self.clock = clock

    def create(self, name: str, email: str) -> Result:
        name = normalize_whitespace(name or "")
        problem = validate_name(name) or validate_email(email)
        if problem:
            return fail(INVALID, problem)
        if self.customers.get_by_email(email):
            return fail(CONFLICT, f"a customer with email {email} already exists")
        customer = Customer(id=new_id("cus"), name=name, email=email, created_at=self.clock())
        self.customers.add(customer)
        return ok(customer)

    def get(self, customer_id: str) -> Result:
        customer = self.customers.get(customer_id)
        if customer is None:
            return fail(NOT_FOUND, f"no customer {customer_id}")
        return ok(customer)

    def list(self) -> Result:
        customers: List[Customer] = self.customers.list_all()
        return ok(customers)
