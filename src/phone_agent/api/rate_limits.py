"""Rate limiting configuration for API endpoints.

Provides rate limiting using slowapi to prevent abuse and ensure fair usage.
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address


# Rate limiter instance - shared across the application
limiter = Limiter(key_func=get_remote_address)


# Rate limit configurations by endpoint type
class RateLimits:
    """Rate limit constants for different endpoint types."""

    # Standard read operations
    READ = "60/minute"

    # Write operations (create, update)
    WRITE = "30/minute"

    # Sensitive operations (authentication, compliance)
    SENSITIVE = "10/minute"

    # Outbound calls (expensive operation)
    OUTBOUND_CALL = "5/minute"

    # Webhooks (high volume from external services)
    WEBHOOK = "200/minute"

    # Analytics/reporting endpoints
    ANALYTICS = "20/minute"

    # Health checks (allow frequent polling)
    HEALTH = "300/minute"
