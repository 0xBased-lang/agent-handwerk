"""IT-Friends Shared Libraries.

Minimal shared utilities for edge AI products.
"""

__version__ = "0.1.0"

from itf_shared.config import load_config
from itf_shared.logging import get_logger, setup_logging
from itf_shared.models import DeviceInfo, Industry

__all__ = [
    "load_config",
    "setup_logging",
    "get_logger",
    "Industry",
    "DeviceInfo",
]
