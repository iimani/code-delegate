"""Service-layer errors.

Service methods return their value directly and raise a ``ServiceError``
subclass for expected failures:

    try:
        customer = service.create(name, email)
    except ServiceError as exc:
        ...  # exc.kind is one of the constants below, exc.message is human readable
"""

NOT_FOUND = "not_found"
INVALID = "invalid"
CONFLICT = "conflict"


class ServiceError(Exception):
    kind = ""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(ServiceError):
    kind = NOT_FOUND


class ValidationError(ServiceError):
    kind = INVALID


class ConflictError(ServiceError):
    kind = CONFLICT
