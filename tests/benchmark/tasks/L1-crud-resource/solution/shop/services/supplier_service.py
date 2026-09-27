import re

from shop.errors import CONFLICT, INVALID, NOT_FOUND, Result, fail, ok
from shop.models import Supplier
from shop.repositories.supplier_repo import SupplierRepository
from shop.services.validation import validate_email, validate_name
from shop.util.clock import Clock
from shop.util.ids import new_id
from shop.util.text import normalize_whitespace

COUNTRY_RE = re.compile(r"^[A-Za-z]{2}$")


class SupplierService:
    def __init__(self, suppliers: SupplierRepository, clock: Clock) -> None:
        self.suppliers = suppliers
        self.clock = clock

    def create(self, name: str, email: str, country: str) -> Result:
        name = normalize_whitespace(name or "")
        problem = validate_name(name) or validate_email(email)
        if not problem and not COUNTRY_RE.match(country or ""):
            problem = f"country must be a two-letter code, got {country!r}"
        if problem:
            return fail(INVALID, problem)
        if self.suppliers.get_by_email(email):
            return fail(CONFLICT, f"a supplier with email {email} already exists")
        supplier = Supplier(id=new_id("sup"), name=name, email=email, country=country.upper(),
                            created_at=self.clock())
        self.suppliers.add(supplier)
        return ok(supplier)

    def get(self, supplier_id: str) -> Result:
        supplier = self.suppliers.get(supplier_id)
        if supplier is None:
            return fail(NOT_FOUND, f"no supplier {supplier_id}")
        return ok(supplier)

    def list(self) -> Result:
        return ok(self.suppliers.list_all())
