from dataclasses import dataclass


@dataclass
class Product:
    id: str
    sku: str
    name: str
    price_cents: int
    active: bool = True
