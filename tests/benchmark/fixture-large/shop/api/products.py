from shop.api.http import Request, Response
from shop.api.responses import bad_request, error_response, json_response
from shop.api.router import Router
from shop.api.serializers import level_to_dict, product_to_dict


def register(router: Router, app) -> None:
    def create(req: Request) -> Response:
        product, err = app.product_service.create(req.body.get("sku", ""), req.body.get("name", ""),
                                                  str(req.body.get("price", "")))
        if err:
            return error_response(err)
        return json_response(product_to_dict(product), 201)

    def get(req: Request) -> Response:
        product, err = app.product_service.get(req.params["id"])
        if err:
            return error_response(err)
        return json_response(product_to_dict(product))

    def list_all(req: Request) -> Response:
        active_only = req.query.get("active") == "1"
        products, _ = app.product_service.list(active_only=active_only)
        return json_response([product_to_dict(p) for p in products])

    def change_price(req: Request) -> Response:
        product, err = app.product_service.change_price(req.params["id"], str(req.body.get("price", "")))
        if err:
            return error_response(err)
        return json_response(product_to_dict(product))

    def deactivate(req: Request) -> Response:
        product, err = app.product_service.deactivate(req.params["id"])
        if err:
            return error_response(err)
        return json_response(product_to_dict(product))

    def stock(req: Request) -> Response:
        level, err = app.inventory_service.level(req.params["id"])
        if err:
            return error_response(err)
        return json_response(level_to_dict(level))

    def receive(req: Request) -> Response:
        quantity = req.body.get("quantity")
        if not isinstance(quantity, int):
            return bad_request("quantity must be an integer")
        level, err = app.inventory_service.receive(req.params["id"], quantity)
        if err:
            return error_response(err)
        return json_response(level_to_dict(level))

    router.add("POST", "/products", create)
    router.add("GET", "/products", list_all)
    router.add("GET", "/products/{id}", get)
    router.add("POST", "/products/{id}/price", change_price)
    router.add("POST", "/products/{id}/deactivate", deactivate)
    router.add("GET", "/products/{id}/stock", stock)
    router.add("POST", "/products/{id}/receive", receive)
