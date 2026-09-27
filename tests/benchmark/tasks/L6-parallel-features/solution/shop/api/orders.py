from shop.api.http import Request, Response
from shop.api.responses import bad_request, error_response, json_response
from shop.api.router import Router
from shop.api.serializers import order_to_dict


def register(router: Router, app) -> None:
    def place(req: Request) -> Response:
        raw_items = req.body.get("items")
        if not isinstance(raw_items, list):
            return bad_request("items must be a list of {product_id, quantity}")
        items = []
        for item in raw_items:
            if not isinstance(item, dict) or "product_id" not in item or "quantity" not in item:
                return bad_request("each item needs product_id and quantity")
            items.append((item["product_id"], item["quantity"]))
        order, err = app.order_service.place(req.body.get("customer_id", ""), items,
                                             req.body.get("discount_code"))
        if err:
            return error_response(err)
        return json_response(order_to_dict(order), 201)

    def get(req: Request) -> Response:
        order, err = app.order_service.get(req.params["id"])
        if err:
            return error_response(err)
        return json_response(order_to_dict(order))

    def cancel(req: Request) -> Response:
        order, err = app.order_service.cancel(req.params["id"])
        if err:
            return error_response(err)
        return json_response(order_to_dict(order))

    router.add("POST", "/orders", place)
    router.add("POST", "/orders/{id}/cancel", cancel)
    router.add("GET", "/orders/{id}", get)
