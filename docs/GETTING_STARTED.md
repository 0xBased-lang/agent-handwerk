# Phone Agent - Developer Getting Started Guide

Quick setup guide for developing on the IT-Friends Phone Agent.

## Prerequisites

- **Python 3.11+** (tested with 3.11-3.13)
- **~4GB disk space** for AI models
- **Audio device** (optional, for telephony features)
- **Git** for version control

## Quick Setup (5 minutes)

### 1. Clone and Navigate to Project

```bash
cd IT-Friends/solutions/phone-agent
```

### 2. Run Setup Script

```bash
chmod +x scripts/setup_dev.sh
./scripts/setup_dev.sh
```

This script:
- Creates/activates a Python virtual environment
- Installs the shared library (`itf-shared`)
- Installs phone-agent with dev dependencies
- Verifies the installation

### 3. Verify Installation

```bash
pytest tests/ -v --tb=short
```

Expected: 140+ tests pass across 5 test files.

## Manual Setup (Alternative)

If the setup script doesn't work, install manually:

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install shared library first
pip install -e ../shared-libs

# Install phone-agent with dev dependencies
pip install -e ".[dev]"

# Download AI models (optional, ~1.5GB)
python scripts/download_models.py
```

## Running the Server

### Development Mode (with auto-reload)

```bash
python -m phone_agent.main --dev
```

Or using uvicorn directly:

```bash
uvicorn phone_agent.api.main:app --reload --port 8080
```

### Access Points

| Endpoint | URL | Description |
|----------|-----|-------------|
| API Docs | http://localhost:8080/docs | Swagger UI |
| Health Check | http://localhost:8080/health | Service status |
| OpenAPI | http://localhost:8080/openapi.json | API schema |

## Project Structure

```
solutions/phone-agent/
├── src/phone_agent/
│   ├── api/              # FastAPI routes and webhooks
│   ├── core/             # Shared utilities and config
│   ├── industry/         # Industry-specific modules
│   │   ├── gesundheit/   # Healthcare (appointments, triage)
│   │   └── handwerk/     # Trades (job intake, dispatch)
│   ├── speech/           # TTS/STT integration
│   └── telephony/        # SIP/FreeSWITCH integration
├── tests/                # pytest test suite
├── configs/              # YAML configuration files
├── scripts/              # Setup and utility scripts
└── docs/                 # Documentation
```

### Key Modules

| Module | Purpose |
|--------|---------|
| `industry/gesundheit/` | Healthcare practice automation |
| `industry/handwerk/` | Trades business automation |
| `api/webhooks.py` | Telephony event handlers |
| `speech/` | Voice synthesis and recognition |

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ITF_ENV` | development | Environment (development/production) |
| `ITF_API_PORT` | 8080 | API server port |
| `ITF_DEBUG` | false | Enable debug logging |
| `ITF_LOG_LEVEL` | INFO | Log level (DEBUG/INFO/WARN/ERROR) |

### Configuration Files

- `configs/development.yaml` - Dev settings
- `configs/production.yaml` - Production settings
- `configs/logging.yaml` - Logging configuration

Example config override:

```bash
export ITF_CONFIG_PATH=/path/to/custom.yaml
python -m phone_agent.main
```

## Running Tests

### Run All Tests

```bash
pytest tests/ -v
```

### Run Specific Test File

```bash
pytest tests/test_healthcare.py -v
```

### Run with Coverage

```bash
pytest tests/ --cov=phone_agent --cov-report=html
```

### Test Structure

| File | Tests |
|------|-------|
| `test_triage.py` | Basic triage logic |
| `test_healthcare.py` | Healthcare module |
| `test_handwerk.py` | Trades module |
| `test_handwerk_triage.py` | Trades triage workflows |
| `test_telephony.py` | SIP/webhook handlers |

## Common Issues

### Import Error: `itf_shared` not found

The shared library isn't installed. Run the setup script:

```bash
./scripts/setup_dev.sh
```

Or manually:

```bash
pip install -e ../shared-libs
```

### Port 8080 Already in Use

Change the port:

```bash
export ITF_API_PORT=8081
python -m phone_agent.main
```

### Model Not Found

Download required models:

```bash
python scripts/download_models.py
```

### Tests Failing with Async Warnings

Some tests may show warnings about unawaited coroutines. This is expected for certain sync test patterns and doesn't affect functionality.

## Development Workflow

### 1. Create Feature Branch

```bash
git checkout -b feature/my-feature
```

### 2. Make Changes

Edit code in `src/phone_agent/`

### 3. Run Tests

```bash
pytest tests/ -v --tb=short
```

### 4. Format Code

```bash
ruff format src/ tests/
ruff check src/ tests/ --fix
```

### 5. Type Check

```bash
mypy src/phone_agent/
```

## Next Steps

- **[Deployment Guide](DEPLOYMENT_RPI5.md)** - Production deployment on Raspberry Pi 5
- **[API Reference](API.md)** - Complete API documentation
- **[Architecture](ARCHITECTURE.md)** - System design overview

## Getting Help

- Check existing issues on GitHub
- Review test files for usage examples
- Consult industry module README files
