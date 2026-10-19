class ServiceError(Exception):
    """A business-rule violation with a readable message for the client."""

    status_code = 400

    def __init__(self, message: str, errors: dict[str, str] | None = None):
        super().__init__(message)
        self.message = message
        self.errors = errors or {}


class NotFound(ServiceError):
    status_code = 404


class Conflict(ServiceError):
    status_code = 409


class ValidationFailed(ServiceError):
    status_code = 422
