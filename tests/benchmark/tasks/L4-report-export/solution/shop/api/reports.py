from shop.api.http import Request, Response
from shop.api.responses import bad_request, json_response
from shop.api.router import Router
from shop.errors import NOT_FOUND
from shop.reports import REPORTS
from shop.reports.export import FORMATS, export
from shop.util.dates import parse_date


def register(router: Router, app) -> None:
    def get(req: Request) -> Response:
        name = req.params["name"]
        if name not in REPORTS:
            return Response(404, {"error": NOT_FOUND, "message": f"no report {name}"})
        fmt = req.query.get("format", "json")
        if fmt not in FORMATS:
            return bad_request(f"unknown format {fmt!r}")
        try:
            if name == "sales":
                if "from" not in req.query or "to" not in req.query:
                    return bad_request("the sales report needs from and to")
                report = REPORTS[name](app, parse_date(req.query["from"]), parse_date(req.query["to"]))
            else:
                report = REPORTS[name](app)
        except ValueError as e:
            return bad_request(str(e))
        return json_response({"name": name, "format": fmt, "content": export(report, fmt)})

    router.add("GET", "/reports/{name}", get)
