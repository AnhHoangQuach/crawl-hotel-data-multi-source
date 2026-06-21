class DomainError(Exception):
    """Base class for errors raised by the domain/application layers.

    The presentation layer maps these to HTTP responses, keeping framework
    concerns (status codes) out of the domain/application code.
    """


class InvalidSourceError(DomainError):
    """Raised when a requested source name isn't a registered provider."""


class CsvParseError(DomainError):
    """Raised when the uploaded CSV doesn't contain a usable hotel list."""


class JobNotFoundError(DomainError):
    """Raised when looking up a job id that doesn't exist."""


class JobNotReadyError(DomainError):
    """Raised when results are requested for a job still pending/running."""
