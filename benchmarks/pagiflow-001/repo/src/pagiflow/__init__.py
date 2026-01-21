"""pagiflow: Resilient REST API pagination collector."""

from pagiflow.client import PaginatedCollector
from pagiflow.cursor import normalize_envelope
from pagiflow.models import PageEnvelope, PaginationConfig, PaginationError

__all__ = [
    "PageEnvelope",
    "PaginatedCollector",
    "PaginationConfig",
    "PaginationError",
    "normalize_envelope",
]
