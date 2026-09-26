"""Maps (method, path pattern) to handler functions. Patterns use {name} placeholders."""
import re
from typing import Callable, List, Pattern, Tuple

from shop.api.http import Request, Response
from shop.errors import NOT_FOUND

Handler = Callable[[Request], Response]


class Router:
    def __init__(self) -> None:
        self.routes: List[Tuple[str, Pattern[str], Handler]] = []

    def add(self, method: str, pattern: str, handler: Handler) -> None:
        regex = "^" + re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", pattern) + "$"
        self.routes.append((method.upper(), re.compile(regex), handler))

    def dispatch(self, request: Request) -> Response:
        path_matched = False
        for method, regex, handler in self.routes:
            match = regex.match(request.path)
            if not match:
                continue
            path_matched = True
            if method == request.method.upper():
                request.params = match.groupdict()
                return handler(request)
        if path_matched:
            return Response(405, {"error": "method_not_allowed", "message": f"{request.method} not allowed"})
        return Response(404, {"error": NOT_FOUND, "message": f"no route for {request.path}"})
