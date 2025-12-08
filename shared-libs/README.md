# ITF Shared Libraries

Minimal shared utilities for IT-Friends edge AI products.

## Philosophy

This package contains **only** genuinely reusable components needed by 2+ products:
- Configuration loading
- Structured logging
- Remote management client
- Common data models

Product-specific code (AI inference, telephony, UI) stays in each product.

## Installation

```bash
pip install -e .
```

## Usage

### Configuration
```python
from itf_shared.config import load_config

config = load_config("configs/production.yaml")
print(config.device_id)
```

### Logging
```python
from itf_shared.logging import setup_logging, get_logger

setup_logging(level="INFO", json_output=True)
log = get_logger(__name__)
log.info("Device started", device_id="pi-001")
```

### Remote Management
```python
from itf_shared.remote import HeartbeatClient

client = HeartbeatClient(device_id="pi-001", interval=60)
await client.start()
```

### Models
```python
from itf_shared.models import Industry, DeviceInfo

device = DeviceInfo(
    device_id="pi-001",
    industry=Industry.GESUNDHEIT,
    product="phone-agent",
)
```

## Structure

```
src/itf_shared/
├── __init__.py
├── config/
│   ├── __init__.py
│   └── loader.py       # YAML/env config loading
├── logging/
│   ├── __init__.py
│   └── setup.py        # structlog configuration
├── remote/
│   ├── __init__.py
│   ├── heartbeat.py    # Device heartbeat
│   └── ota.py          # OTA update client
└── models/
    ├── __init__.py
    ├── industry.py     # Industry enum
    └── device.py       # Device info model
```
