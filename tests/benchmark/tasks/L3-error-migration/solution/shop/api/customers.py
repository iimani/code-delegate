from shop.api.http import Request, Response
from shop.api.responses import error_response, json_response
from shop.api.router import Router
from shop.api.serializers import customer_to_dict, order_to_dict
from shop.errors import ServiceError


def register(router: Router, app) -> None:
    def create(req: Request) -> Response:
        try:
            customer = app.customer_service.create(req.body.get("name", ""), req.body.get("email", ""))
        except ServiceError as exc:
            return error_response(exc)
        return json_response(customer_to_dict(customer), 201)

    def get(req: Request) -> Response:
        try:
            customer = app.customer_service.get(req.params["id"])
        except ServiceError as exc:
            return error_response(exc)
        return json_response(customer_to_dict(customer))

    def list_all(req: Request) -> Response:
        return json_response([customer_to_dict(c) for c in app.customer_service.list()])

    def orders(req: Request) -> Response:
        try:
            found = app.order_service.list_for_customer(req.params["id"])
        except ServiceError as exc:
            return error_response(exc)
        return json_response([order_to_dict(o) for o in found])

    router.add("POST", "/customers", create)
    router.add("GET", "/customers", list_all)
    router.add("GET", "/customers/{id}", get)
    router.add("GET", "/customers/{id}/orders", orders)
