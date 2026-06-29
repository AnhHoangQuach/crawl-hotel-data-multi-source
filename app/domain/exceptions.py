class DomainError(Exception):
    """Base class for errors raised by the domain/application layers.

    The presentation layer maps these to HTTP responses, keeping framework
    concerns (status codes) out of the domain/application code.
    """


class InvalidSourceError(DomainError):
    """Raised when a requested source name isn't a registered provider."""
