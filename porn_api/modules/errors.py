"""Provider errors retain the shared backend's exception contracts."""

from base_api.modules.errors import (
    BotDetection,
    DownloadFailed,
    NetworkError,
    NotFound,
    ProxyError,
    ScraperException,
    UnknownNetworkError,
    VideoUnavailable,
)


class ParseError(ScraperException):
    """The response does not match the requested resource or expected layout."""


__all__ = [
    "BotDetection",
    "DownloadFailed",
    "NetworkError",
    "NotFound",
    "ProxyError",
    "ScraperException",
    "UnknownNetworkError",
    "VideoUnavailable",
    "ParseError",
]
