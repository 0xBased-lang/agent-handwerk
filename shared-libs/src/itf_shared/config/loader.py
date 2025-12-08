"""Configuration loader using Dynaconf."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dynaconf import Dynaconf
from pydantic import BaseModel


class Settings(BaseModel):
    """Base settings model for all products."""

    # Device identification
    device_id: str = ""
    device_name: str = "pi-unnamed"

    # Environment
    environment: str = "development"
    debug: bool = False

    # Logging
    log_level: str = "INFO"
    log_json: bool = False

    # Remote management
    remote_enabled: bool = True
    heartbeat_interval: int = 60  # seconds

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8080

    class Config:
        extra = "allow"  # Allow product-specific fields


def load_config(
    config_path: str | Path | None = None,
    env: str | None = None,
) -> Settings:
    """Load configuration from YAML files and environment variables.

    Priority (highest to lowest):
    1. Environment variables (ITF_*)
    2. {env}.yaml (e.g., production.yaml)
    3. default.yaml
    4. Built-in defaults

    Args:
        config_path: Path to config directory or specific file
        env: Environment name (development, production, etc.)

    Returns:
        Settings object with loaded configuration
    """
    # Determine environment
    environment = env or os.getenv("ITF_ENV", "development")

    # Determine config path
    if config_path is None:
        config_path = Path.cwd() / "configs"
    else:
        config_path = Path(config_path)

    # Build settings file list
    settings_files: list[str] = []
    if config_path.is_dir():
        default_file = config_path / "default.yaml"
        env_file = config_path / f"{environment}.yaml"
        if default_file.exists():
            settings_files.append(str(default_file))
        if env_file.exists():
            settings_files.append(str(env_file))
    elif config_path.is_file():
        settings_files.append(str(config_path))

    # Load with Dynaconf
    dynaconf_settings = Dynaconf(
        envvar_prefix="ITF",
        settings_files=settings_files,
        environments=False,  # We handle environments manually
        load_dotenv=True,
    )

    # Convert to Pydantic model
    config_dict: dict[str, Any] = {}
    for key in dynaconf_settings.keys():
        if not key.startswith("_"):
            config_dict[key.lower()] = dynaconf_settings[key]

    # Add environment
    config_dict["environment"] = environment

    # Generate device_id if not set
    if not config_dict.get("device_id"):
        config_dict["device_id"] = _generate_device_id()

    return Settings(**config_dict)


def _generate_device_id() -> str:
    """Generate a unique device ID from Raspberry Pi serial number."""
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("Serial"):
                    return f"pi-{line.split(':')[1].strip()[-8:]}"
    except (FileNotFoundError, IndexError):
        pass

    # Fallback to hostname
    import socket

    return f"dev-{socket.gethostname()}"
