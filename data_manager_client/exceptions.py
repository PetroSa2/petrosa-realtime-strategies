"""Exceptions raised by the data-manager HTTP client."""


class ConnectionError(Exception):
    """The data-manager service could not be reached or returned an error."""
