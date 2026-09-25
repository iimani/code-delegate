from typing import Any

from shop.api.http import Response
from shop.errors import CONFLICT, INVALID, NOT_FOUND, ServiceError

STATUS_BY_KIND = {NOT_FOUND: 404, INVALID: 400, CONFLICT: 409}


def json_response(body: Any, status: int = 200) -> Response:
    return Response(status, body)


def error_response(exc: ServiceError) -> Response:
    return Response(STATUS_BY_KIND[exc.kind], {"error": exc.kind, "message": exc.message})


def bad_request(message: str) -> Response:
    return Response(400, {"error": INVALID, "message": message})
