from shop.api.http import Request, Response
from shop.api.responses import error_response, json_response
from shop.api.router import Router
from shop.api.serializers import customer_to_dict, order_to_dict


def register(router: Router, app) -> None:
    def create(req: Request) -> Response:
        customer, err = app.customer_service.create(req.body.get("name", ""), req.body.get("email", ""))
        if err:
            return error_response(err)
        return json_response(customer_to_dict(customer), 201)

    def get(req: Request) -> Response:
        customer, err = app.customer_service.get(req.params["id"])
        if err:
            return error_response(err)
        return json_response(customer_to_dict(customer))

    def list_all(req: Request) -> Response:
        customers, _ = app.customer_service.list()
        return json_response([customer_to_dict(c) for c in customers])

    def orders(req: Request) -> Response:
        found, err = app.order_service.list_for_customer(req.params["id"])
        if err:
            return error_response(err)
        return json_response([order_to_dict(o) for o in found])

    router.add("POST", "/customers", create)
    router.add("GET", "/customers", list_all)
    router.add("GET", "/customers/{id}", get)
    router.add("GET", "/customers/{id}/orders", orders)
