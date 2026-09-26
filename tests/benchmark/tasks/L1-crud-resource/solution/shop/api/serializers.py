"""Model -> JSON-ready dict. Money stays in integer cents; timestamps become ISO strings."""
from typing import Any, Dict

from shop.models import Customer, InventoryLevel, Order, Product, Supplier
from shop.util.dates import to_iso


def customer_to_dict(c: Customer) -> Dict[str, Any]:
    return {"id": c.id, "name": c.name, "email": c.email, "created_at": to_iso(c.created_at)}


def supplier_to_dict(s: Supplier) -> Dict[str, Any]:
    return {"id": s.id, "name": s.name, "email": s.email, "country": s.country,
            "created_at": to_iso(s.created_at)}


def product_to_dict(p: Product) -> Dict[str, Any]:
    return {"id": p.id, "sku": p.sku, "name": p.name, "price_cents": p.price_cents, "active": p.active}


def level_to_dict(level: InventoryLevel) -> Dict[str, Any]:
    return {"product_id": level.product_id, "on_hand": level.on_hand, "reserved": level.reserved,
            "available": level.available}


def order_to_dict(o: Order) -> Dict[str, Any]:
    return {
        "id": o.id, "customer_id": o.customer_id, "status": o.status, "created_at": to_iso(o.created_at),
        "subtotal_cents": o.subtotal_cents, "discount_cents": o.discount_cents, "vat_cents": o.vat_cents,
        "total_cents": o.total_cents, "discount_code": o.discount_code,
        "lines": [{"product_id": l.product_id, "quantity": l.quantity, "unit_price_cents": l.unit_price_cents}
                  for l in o.lines],
    }
