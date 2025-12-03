# IT-Friends Phone Agent

AI-powered telephone system for German SME healthcare automation, running locally on Raspberry Pi 5.

## Features

### Core AI Pipeline
- **Speech-to-Text**: German-optimized Whisper (`distil-whisper-large-v3-german`)
- **Language Model**: Llama 3.2 1B for natural German conversation
- **Text-to-Speech**: Piper TTS with Thorsten German voice
- **Full local processing**: No cloud dependencies, DSGVO compliant

### Healthcare Functionality
- **Intelligent Triage**: Symptom assessment based on German ambulatory care standards
- **Emergency Detection**: Automatic recognition of life-threatening conditions
- **Smart Scheduling**: Calendar integration with preference matching
- **Recall Campaigns**: Preventive care, vaccination, and follow-up reminders
- **DSGVO Compliance**: Consent management, audit logging, data protection

### Telephony Integration
- **FreeSWITCH**: Full PBX integration via ESL
- **SIP Webhooks**: Compatible with Twilio, sipgate, and generic SIP providers
- **Audio Bridge**: Bidirectional streaming for real-time conversation

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                       Phone Agent                                │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                       FastAPI                              │  │
│  │  /health  /calls  /appointments  /triage  /recall         │  │
│  └───────────────────────────────────────────────────────────┘  │
│                            │                                     │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                    Core Logic                              │  │
│  │  CallHandler  ConversationEngine  AudioPipeline           │  │
│  └───────────────────────────────────────────────────────────┘  │
│         │              │              │                          │
│  ┌──────┴──────┐ ┌─────┴─────┐ ┌──────┴──────┐                 │
│  │     AI      │ │ Telephony │ │   Industry  │                 │
│  │ STT LLM TTS │ │ SIP Audio │ │ Gesundheit  │                 │
│  └─────────────┘ └───────────┘ └─────────────┘                 │
│                                      │                          │
│                        ┌─────────────┴─────────────┐           │
│                        │      Healthcare Logic      │           │
│                        │ Triage Scheduling Recall  │           │
│                        │ Compliance Conversation   │           │
│                        └───────────────────────────┘           │
└─────────────────────────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites
- Python 3.11+
- Raspberry Pi 5 (8GB recommended) or development machine
- Docker (optional, for production deployment)

### Installation

```bash
# Clone the repository
git clone https://github.com/it-friends/phone-agent
cd phone-agent

# Install shared library
cd ../shared-libs
pip install -e .

# Install phone agent
cd ../phone-agent
pip install -e ".[dev]"

# Download AI models (~1.5GB)
python scripts/download_models.py
```

### Running the Server

```bash
# Development mode
uvicorn phone_agent.main:app --reload

# Production mode
phone-agent
```

### Testing

```bash
# Run all tests
pytest

# Run specific test modules
pytest tests/test_healthcare.py -v
pytest tests/test_triage.py -v

# Test CLI tools
python -m phone_agent.cli test-stt
python -m phone_agent.cli test-llm
python -m phone_agent.cli test-tts
python -m phone_agent.cli chat
```

## Documentation

- **[Getting Started](docs/GETTING_STARTED.md)** - Developer setup guide (5-minute quick start)
- **[Raspberry Pi 5 Deployment](docs/DEPLOYMENT_RPI5.md)** - Production deployment guide

## API Endpoints

### Health
- `GET /health` - Health check
- `GET /health/detailed` - Detailed system status

### Calls
- `POST /api/v1/calls` - Initiate a call
- `GET /api/v1/calls/{call_id}` - Get call status
- `POST /api/v1/calls/{call_id}/end` - End a call

### Appointments
- `POST /api/v1/appointments` - Create appointment
- `GET /api/v1/appointments` - List appointments
- `DELETE /api/v1/appointments/{id}` - Cancel appointment

### Triage
- `POST /api/v1/triage` - Perform triage assessment
- `POST /api/v1/triage/extract-symptoms` - Extract symptoms from text
- `GET /api/v1/triage/urgency-levels` - Get urgency level definitions

### Recall Campaigns
- `POST /api/v1/recall/campaigns` - Create campaign
- `POST /api/v1/recall/campaigns/{id}/patients` - Add patient to campaign
- `GET /api/v1/recall/campaigns/{id}/next-patient` - Get next patient to call
- `GET /api/v1/recall/campaigns/{id}/stats` - Get campaign statistics

### Webhooks
- `POST /api/v1/webhooks/call/incoming` - Handle incoming calls
- `POST /api/v1/webhooks/twilio/voice` - Twilio voice webhook
- `POST /api/v1/webhooks/sipgate/call` - sipgate webhook
- `WS /api/v1/ws/audio/{call_id}` - WebSocket audio streaming

## Configuration

Configuration is loaded from `configs/default.yaml` and can be overridden with environment variables.

```yaml
# Device identification
device_name: "phone-agent-prod"
environment: production

# AI Settings
ai:
  stt:
    model: "primeline/whisper-large-v3-german"
    device: "cpu"  # or "npu" for Raspberry Pi AI Kit
  llm:
    model: "models/llama-3.2-1b-q4.gguf"
    n_ctx: 4096
  tts:
    model: "thorsten_de"
    speaker_id: 0

# Telephony
telephony:
  enabled: true
  backend: "freeswitch"  # or "webhook"
  freeswitch:
    host: "127.0.0.1"
    port: 8021
    password: "${ITF_FS_PASSWORD}"

# Practice settings
practice:
  name: "Dr. Mustermann"
  phone: "+49 30 12345678"
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ITF_DEVICE_ID` | Unique device identifier | auto-generated |
| `ITF_ENVIRONMENT` | Environment (development/production) | development |
| `ITF_API_PORT` | API server port | 8080 |
| `ITF_FS_PASSWORD` | FreeSWITCH ESL password | - |
| `ITF_TAILSCALE_KEY` | Tailscale auth key | - |

## Project Structure

```
phone-agent/
├── configs/              # Configuration files
│   ├── default.yaml
│   └── production.yaml
├── prompts/              # Jinja2 templates (German)
│   ├── greeting.jinja2
│   ├── appointment_confirmation.jinja2
│   └── sms_reminder.jinja2
├── scripts/
│   ├── download_models.py
│   ├── setup_freeswitch.sh
│   └── setup_sipgate.md
├── src/phone_agent/
│   ├── api/              # FastAPI routers
│   │   ├── health.py
│   │   ├── calls.py
│   │   ├── appointments.py
│   │   ├── triage.py
│   │   ├── recall.py
│   │   └── webhooks.py
│   ├── ai/               # AI components
│   │   ├── stt.py        # Speech-to-Text
│   │   ├── llm.py        # Language Model
│   │   └── tts.py        # Text-to-Speech
│   ├── core/             # Core business logic
│   │   ├── audio.py      # Audio pipeline
│   │   ├── conversation.py
│   │   └── call_handler.py
│   ├── telephony/        # Telephony integration
│   │   ├── sip_client.py
│   │   ├── freeswitch.py
│   │   ├── audio_bridge.py
│   │   └── service.py
│   ├── industry/gesundheit/  # Healthcare logic
│   │   ├── prompts.py        # German prompts
│   │   ├── workflows.py      # Basic workflows
│   │   ├── triage.py         # Advanced triage
│   │   ├── scheduling.py     # Appointment scheduling
│   │   ├── recall.py         # Recall campaigns
│   │   ├── compliance.py     # DSGVO compliance
│   │   └── conversation.py   # Conversation manager
│   ├── config.py
│   ├── main.py
│   └── cli.py
├── tests/
│   ├── conftest.py
│   ├── test_triage.py
│   ├── test_healthcare.py
│   └── test_telephony.py
├── docker-compose.yml
├── Dockerfile
└── pyproject.toml
```

## Healthcare Triage System

The triage system follows German ambulatory care standards (KBV Bereitschaftsdienst).

### Urgency Levels

| Level | German | Response Time | Action |
|-------|--------|---------------|--------|
| Emergency | Notfall | Immediate | Call 112 |
| Very Urgent | Sehr dringend | < 10 min | Immediate appointment |
| Urgent | Dringend | < 30 min | Same-day appointment |
| Standard | Normal | < 90 min | Regular appointment |
| Non-urgent | Nicht dringend | - | Scheduled appointment |

### Emergency Detection

Automatic detection of emergency keywords:
- Chest pain (Brustschmerzen)
- Breathing difficulty (Atemnot)
- Stroke symptoms (Lähmung, Sprachstörung)
- Severe bleeding (Starke Blutung)
- Unconsciousness (Bewusstlos)

### Patient Risk Factors

Risk scoring considers:
- Age (< 2 or > 75 years: +50%)
- Pregnancy (+30%)
- Diabetes (+20%)
- Immunocompromised (+50%)
- Heart condition (+30%)

## Recall Campaigns

Built-in campaign types:

| Type | German | Use Case |
|------|--------|----------|
| Preventive | Vorsorge | Check-up 35+ |
| Vaccination | Impfung | Flu, COVID, Tetanus |
| Chronic | DMP | Quarterly follow-ups |
| No-show | Verpasst | Missed appointments |
| Lab Results | Labor | Result discussions |

## DSGVO Compliance

### Consent Management

Required consents for AI phone calls:
- `PHONE_CONTACT` - Telephone contact permission
- `AI_PROCESSING` - AI-assisted communication
- `VOICE_RECORDING` - Call recording (optional)

### Data Retention

| Data Type | Retention | Legal Basis |
|-----------|-----------|-------------|
| Medical records | 10 years | § 10 MBO-Ä, § 630f BGB |
| Call recordings | 1 year | Art. 6 DSGVO |
| Consent records | 11 years | Art. 7 DSGVO |
| Audit logs | 5 years | Art. 5, 30 DSGVO |

### Audit Logging

All patient data access is logged with:
- Timestamp
- Actor (user/AI agent)
- Action type
- Resource ID
- Checksum for integrity

## Deployment

### Docker

```bash
# Build image
docker build -t itf-phone-agent .

# Run container
docker-compose up -d
```

### Raspberry Pi 5

```bash
# Initial setup (run once)
cd infrastructure/ansible
ansible-playbook playbooks/initial-setup.yml

# Deploy phone agent
ansible-playbook playbooks/deploy-phone-agent.yml

# Health check
ansible-playbook playbooks/health-check.yml
```

### Tailscale VPN

All devices communicate via Tailscale VPN. Configure with:
```bash
sudo tailscale up --authkey=$TAILSCALE_KEY --hostname=phone-agent-001
```

## Performance

### Target Metrics (Raspberry Pi 5)

| Component | Target | Measured |
|-----------|--------|----------|
| STT latency | < 500ms | ~400ms |
| LLM inference | < 1s | ~800ms |
| TTS synthesis | < 300ms | ~250ms |
| End-to-end | < 2s | ~1.5s |

### AI Models

| Component | Model | Size | Notes |
|-----------|-------|------|-------|
| STT | distil-whisper-large-v3-german | ~750MB | German-optimized |
| LLM | Llama 3.2 1B-Instruct Q4_K_M | ~800MB | Quantized for Pi |
| TTS | Piper thorsten_de medium | ~30MB | German voice |

### Memory Usage

- STT model: ~1GB
- LLM model: ~1.5GB
- TTS model: ~50MB
- Application: ~200MB
- **Total**: ~3GB (fits in 8GB Pi)

## Hardware Requirements

- Raspberry Pi 5 8GB
- USB Audio Interface
- SIP Gateway (Grandstream HT801 ~45€)
- Optional: AI Accelerator (Hailo-8L)

## Development

```bash
# Run tests
pytest

# Type checking
mypy src/

# Linting
ruff check src/

# Format code
ruff format src/
```

## License

MIT License - see LICENSE file.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Run tests: `pytest`
4. Run linting: `ruff check .`
5. Submit a pull request
