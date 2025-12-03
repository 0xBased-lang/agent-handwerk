"""Industry-specific configurations and workflows.

Supported industries:
- gesundheit: Healthcare/medical practices
- handwerk: Trades businesses (plumbing, electrical, etc.)
"""
from phone_agent.industry import gesundheit
from phone_agent.industry import handwerk

__all__ = [
    "gesundheit",
    "handwerk",
]
