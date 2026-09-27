"""Command-line interface: python -m shop.cli.main --db shop.db <command> ...

Exit status 0 on success, 1 on a service error (message on stderr), 2 on usage errors.
"""
import argparse
import sys
from typing import List, Optional, TextIO

from shop.app import build_app
from shop.reports import REPORTS
from shop.reports.base import render_text
from shop.util.dates import parse_date
from shop.util.money import format_cents


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="shop")
    p.add_argument("--db", default="shop.db", help="sqlite database file")
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("customers").add_subparsers(dest="action", required=True)
    add = c.add_parser("add")
    add.add_argument("name")
    add.add_argument("email")
    c.add_parser("list")

    pr = sub.add_parser("products").add_subparsers(dest="action", required=True)
    add = pr.add_parser("add")
    add.add_argument("sku")
    add.add_argument("name")
    add.add_argument("price")
    lst = pr.add_parser("list")
    lst.add_argument("--all", action="store_true", help="include inactive products")
    price = pr.add_parser("price")
    price.add_argument("product_id")
    price.add_argument("price")

    inv = sub.add_parser("inventory").add_subparsers(dest="action", required=True)
    rec = inv.add_parser("receive")
    rec.add_argument("product_id")
    rec.add_argument("quantity", type=int)

    o = sub.add_parser("orders").add_subparsers(dest="action", required=True)
    place = o.add_parser("place")
    place.add_argument("customer_id")
    place.add_argument("items", nargs="+", metavar="PRODUCT_ID:QTY")
    place.add_argument("--code", help="discount code")

    r = sub.add_parser("report")
    r.add_argument("name", choices=sorted(REPORTS))
    r.add_argument("--from", dest="start", help="YYYY-MM-DD (sales report)")
    r.add_argument("--to", dest="end", help="YYYY-MM-DD (sales report)")
    return p


def _parse_items(raw: List[str]):
    items = []
    for entry in raw:
        product_id, sep, qty = entry.rpartition(":")
        if not sep or not qty.isdigit():
            raise ValueError(f"expected PRODUCT_ID:QTY, got {entry!r}")
        items.append((product_id, int(qty)))
    return items


def main(argv: Optional[List[str]] = None, out: TextIO = sys.stdout, err: TextIO = sys.stderr) -> int:
    args = _parser().parse_args(argv)
    app = build_app(args.db)

    def fail(message: str) -> int:
        print(f"error: {message}", file=err)
        return 1

    if args.command == "customers":
        if args.action == "add":
            customer, e = app.customer_service.create(args.name, args.email)
            if e:
                return fail(e.message)
            print(customer.id, file=out)
        else:
            customers, _ = app.customer_service.list()
            for c in customers:
                print(f"{c.id}\t{c.name}\t{c.email}", file=out)
    elif args.command == "products":
        if args.action == "add":
            product, e = app.product_service.create(args.sku, args.name, args.price)
            if e:
                return fail(e.message)
            print(product.id, file=out)
        elif args.action == "list":
            products, _ = app.product_service.list(active_only=not args.all)
            for p in products:
                print(f"{p.id}\t{p.sku}\t{p.name}\t{format_cents(p.price_cents)}", file=out)
        else:
            product, e = app.product_service.change_price(args.product_id, args.price)
            if e:
                return fail(e.message)
            print(format_cents(product.price_cents), file=out)
    elif args.command == "inventory":
        level, e = app.inventory_service.receive(args.product_id, args.quantity)
        if e:
            return fail(e.message)
        print(f"on_hand={level.on_hand} available={level.available}", file=out)
    elif args.command == "orders":
        try:
            items = _parse_items(args.items)
        except ValueError as e:
            return fail(str(e))
        order, e = app.order_service.place(args.customer_id, items, args.code)
        if e:
            return fail(e.message)
        print(f"{order.id}\t{format_cents(order.total_cents)}", file=out)
    elif args.command == "report":
        builder = REPORTS[args.name]
        try:
            if args.name == "sales":
                if not args.start or not args.end:
                    return fail("the sales report needs --from and --to")
                report = builder(app, parse_date(args.start), parse_date(args.end))
            else:
                report = builder(app)
        except ValueError as e:
            return fail(str(e))
        out.write(render_text(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
