from shop.api.http import Request, Response
from shop.api.responses import error_response, json_response
from shop.api.router import Router
from shop.api.serializers import supplier_to_dict


def register(router: Router, app) -> None:
    def create(req: Request) -> Response:
        supplier, err = app.supplier_service.create(req.body.get("name", ""), req.body.get("email", ""),
                                                    req.body.get("country", ""))
        if err:
            return error_response(err)
        return json_response(supplier_to_dict(supplier), 201)

    def get(req: Request) -> Response:
        supplier, err = app.supplier_service.get(req.params["id"])
        if err:
            return error_response(err)
        return json_response(supplier_to_dict(supplier))

    def list_all(req: Request) -> Response:
        suppliers, _ = app.supplier_service.list()
        return json_response([supplier_to_dict(s) for s in suppliers])

    router.add("POST", "/suppliers", create)
    router.add("GET", "/suppliers", list_all)
    router.add("GET", "/suppliers/{id}", get)
