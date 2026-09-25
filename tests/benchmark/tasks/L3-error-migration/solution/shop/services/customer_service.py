from typing import List

from shop.errors import ConflictError, NotFoundError, ValidationError
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

    def create(self, name: str, email: str) -> Customer:
        name = normalize_whitespace(name or "")
        problem = validate_name(name) or validate_email(email)
        if problem:
            raise ValidationError(problem)
        if self.customers.get_by_email(email):
            raise ConflictError(f"a customer with email {email} already exists")
        customer = Customer(id=new_id("cus"), name=name, email=email, created_at=self.clock())
        self.customers.add(customer)
        return customer

    def get(self, customer_id: str) -> Customer:
        customer = self.customers.get(customer_id)
        if customer is None:
            raise NotFoundError(f"no customer {customer_id}")
        return customer

    def list(self) -> List[Customer]:
        return self.customers.list_all()
