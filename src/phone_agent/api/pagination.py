"""Pagination constants and utilities.

Provides consistent pagination defaults across all API endpoints.
"""

from typing import Annotated

from fastapi import Query
from pydantic import BaseModel, Field


# ============================================================================
# Pagination Constants
# ============================================================================

# Default values
DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 20

# Limits for standard endpoints
MIN_PAGE_SIZE = 1
MAX_PAGE_SIZE = 100

# Limits for bulk/export endpoints
MAX_EXPORT_SIZE = 10000
MAX_BULK_SIZE = 500

# Limits for analytics/reporting endpoints
MAX_ANALYTICS_LIMIT = 1000


# ============================================================================
# Pagination Query Parameters (FastAPI Dependencies)
# ============================================================================

PageParam = Annotated[
    int,
    Query(
        default=DEFAULT_PAGE,
        ge=1,
        description="Page number (1-indexed)",
    ),
]

PageSizeParam = Annotated[
    int,
    Query(
        default=DEFAULT_PAGE_SIZE,
        ge=MIN_PAGE_SIZE,
        le=MAX_PAGE_SIZE,
        description=f"Number of results per page (max {MAX_PAGE_SIZE})",
    ),
]

LimitParam = Annotated[
    int,
    Query(
        default=DEFAULT_PAGE_SIZE,
        ge=MIN_PAGE_SIZE,
        le=MAX_PAGE_SIZE,
        description=f"Maximum number of results (max {MAX_PAGE_SIZE})",
    ),
]

BulkLimitParam = Annotated[
    int,
    Query(
        default=100,
        ge=MIN_PAGE_SIZE,
        le=MAX_BULK_SIZE,
        description=f"Maximum number of results for bulk operations (max {MAX_BULK_SIZE})",
    ),
]


# ============================================================================
# Pagination Response Models
# ============================================================================


class PaginationMeta(BaseModel):
    """Pagination metadata for response."""

    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Number of items per page")
    total: int = Field(..., description="Total number of items")
    total_pages: int = Field(..., description="Total number of pages")
    has_next: bool = Field(..., description="Whether there is a next page")
    has_prev: bool = Field(..., description="Whether there is a previous page")

    @classmethod
    def from_params(cls, page: int, page_size: int, total: int) -> "PaginationMeta":
        """Create pagination metadata from query parameters."""
        total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
        return cls(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1,
        )


# ============================================================================
# Utility Functions
# ============================================================================


def calculate_offset(page: int, page_size: int) -> int:
    """Calculate the offset for database queries.

    Args:
        page: Page number (1-indexed)
        page_size: Number of items per page

    Returns:
        Offset for database skip parameter
    """
    return (page - 1) * page_size


def validate_page_bounds(page: int, page_size: int, total: int) -> int:
    """Validate and adjust page number to be within bounds.

    Args:
        page: Requested page number
        page_size: Number of items per page
        total: Total number of items

    Returns:
        Adjusted page number (always >= 1, <= total_pages)
    """
    if total == 0:
        return 1

    total_pages = (total + page_size - 1) // page_size
    return max(1, min(page, total_pages))
