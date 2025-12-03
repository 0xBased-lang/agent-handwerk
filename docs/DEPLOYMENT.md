# IT-Friends Phone Agent - Deployment Guide

Complete deployment guide for production environments.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Prerequisites](#prerequisites)
3. [Configuration](#configuration)
4. [Deployment Options](#deployment-options)
5. [Telephony Setup](#telephony-setup)
6. [SMS & Email Integration](#sms--email-integration)
7. [Monitoring](#monitoring)
8. [Security Hardening](#security-hardening)
9. [Troubleshooting](#troubleshooting)

---

## Quick Start

### 1. Clone and Configure

```bash
# Clone repository
git clone https://github.com/IT-Friends/phone-agent.git
cd phone-agent

# Copy environment template
cp .env.example .env

# Edit with your credentials
nano .env
```

### 2. Download AI Models

```bash
# Create models directory
mkdir -p models/{whisper,llm,tts}

# Download models (see docs/AI_MODELS.md for details)
./scripts/download_models.sh
```

### 3. Start Services

```bash
# Development
docker compose up -d

# Production with monitoring
docker compose -f docker-compose.prod.yml --profile monitoring up -d
```

### 4. Verify Deployment

```bash
# Check health
curl http://localhost:8080/health

# View logs
docker logs -f itf-phone-agent
```

---

## Prerequisites

### Hardware Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| CPU | 4 cores (ARM64/x64) | Raspberry Pi 5 / 8 cores |
| RAM | 4GB | 8GB |
| Storage | 16GB | 32GB+ SSD |
| Network | 10 Mbps | 100 Mbps |

### Software Requirements

- Docker 24+ and Docker Compose v2
- Python 3.11+ (for native installation)
- Domain name with SSL (for webhooks)

---

## Configuration

### Environment Variables

All configuration uses the `ITF_` prefix. Nested values use double underscore:

```bash
# Simple value
ITF_LOG_LEVEL=INFO

# Nested value
ITF_TELEPHONY__TWILIO__ACCOUNT_SID=AC...
```

### Configuration Files

```
configs/
├── default.yaml      # Base configuration
├── production.yaml   # Production overrides
└── telephony.yaml    # Telephony-specific settings
```

### Priority Order

1. Environment variables (`ITF_*`)
2. Environment-specific YAML (`production.yaml`)
3. Default YAML (`default.yaml`)

---

## Deployment Options

### Option A: Docker (Recommended)

```bash
# Basic deployment
docker compose up -d

# With Traefik proxy (SSL)
docker compose -f docker-compose.prod.yml --profile proxy up -d

# With monitoring stack
docker compose -f docker-compose.prod.yml --profile monitoring up -d

# Full production (all profiles)
docker compose -f docker-compose.prod.yml \
  --profile proxy \
  --profile monitoring \
  up -d
```

### Option B: Native Installation

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -e .

# Run application
ITF_ENV=production uvicorn phone_agent.main:app --host 0.0.0.0 --port 8080
```

### Option C: Raspberry Pi Appliance

See `docs/RASPBERRY_PI_SETUP.md` for complete appliance setup.

---

## Telephony Setup

### Twilio (Cloud VoIP)

1. **Create Twilio Account**
   - Sign up at https://www.twilio.com
   - Get German phone number (+49...)

2. **Configure Environment**
   ```bash
   ITF_TELEPHONY__TWILIO__ENABLED=true
   ITF_TELEPHONY__TWILIO__ACCOUNT_SID=ACxxxxxxxxxx
   ITF_TELEPHONY__TWILIO__AUTH_TOKEN=your_auth_token
   ITF_TELEPHONY__TWILIO__FROM_NUMBER=+49XXXXXXXXXX
   ITF_TELEPHONY__TWILIO__WEBHOOK_URL=https://your-domain.com/api/v1/webhooks/twilio
   ```

3. **Configure Twilio Webhooks**
   - Voice URL: `https://your-domain.com/api/v1/webhooks/twilio/voice`
   - SMS URL: `https://your-domain.com/api/v1/webhooks/twilio/sms`
   - Status Callback: `https://your-domain.com/api/v1/webhooks/sms/twilio/status`

### sipgate (German VoIP)

1. **Create sipgate Account**
   - Sign up at https://www.sipgate.de
   - Enable API access in settings

2. **Configure Environment**
   ```bash
   ITF_TELEPHONY__SIPGATE__ENABLED=true
   ITF_TELEPHONY__SIPGATE__USERNAME=your_sipid
   ITF_TELEPHONY__SIPGATE__PASSWORD=your_password
   ITF_TELEPHONY__SIPGATE__API_TOKEN=your_api_token
   ITF_TELEPHONY__SIPGATE__CALLER_ID=+49XXXXXXXXXX
   ```

### FreeSWITCH (Self-hosted)

1. **Install FreeSWITCH**
   ```bash
   apt-get install freeswitch freeswitch-mod-commands
   ```

2. **Configure Environment**
   ```bash
   ITF_TELEPHONY__FREESWITCH__ENABLED=true
   ITF_TELEPHONY__FREESWITCH__HOST=127.0.0.1
   ITF_TELEPHONY__FREESWITCH__PORT=8021
   ITF_TELEPHONY__FREESWITCH__PASSWORD=your_esl_password
   ```

---

## SMS & Email Integration

### SMS via Twilio

Uses the same Twilio credentials as telephony:

```bash
ITF_INTEGRATIONS__SMS__ENABLED=true
ITF_INTEGRATIONS__SMS__PROVIDER=twilio
```

### Email via SendGrid (Recommended)

1. **Create SendGrid Account**
   - Sign up at https://sendgrid.com
   - Create API key with Mail Send permissions

2. **Configure Environment**
   ```bash
   ITF_INTEGRATIONS__EMAIL__ENABLED=true
   ITF_INTEGRATIONS__EMAIL__PROVIDER=sendgrid
   ITF_INTEGRATIONS__EMAIL__FROM_EMAIL=noreply@praxis-name.de
   ITF_INTEGRATIONS__EMAIL__FROM_NAME=Praxis Dr. Name
   ITF_INTEGRATIONS__EMAIL__SENDGRID__API_KEY=SG.xxxxx
   ITF_INTEGRATIONS__EMAIL__SENDGRID__WEBHOOK_URL=https://your-domain.com/api/v1/webhooks/email/sendgrid/events
   ```

3. **Configure SendGrid Webhooks**
   - Event Webhook URL: `https://your-domain.com/api/v1/webhooks/email/sendgrid/events`
   - Events: Delivered, Opened, Clicked, Bounced, Spam Report

### Email via SMTP

```bash
ITF_INTEGRATIONS__EMAIL__ENABLED=true
ITF_INTEGRATIONS__EMAIL__PROVIDER=smtp
ITF_INTEGRATIONS__EMAIL__FROM_EMAIL=noreply@praxis-name.de
ITF_INTEGRATIONS__EMAIL__FROM_NAME=Praxis Dr. Name
ITF_INTEGRATIONS__EMAIL__SMTP__HOST=smtp.gmail.com
ITF_INTEGRATIONS__EMAIL__SMTP__PORT=587
ITF_INTEGRATIONS__EMAIL__SMTP__USERNAME=your_email
ITF_INTEGRATIONS__EMAIL__SMTP__PASSWORD=your_app_password
ITF_INTEGRATIONS__EMAIL__SMTP__USE_TLS=true
```

---

## Monitoring

### Enable Monitoring Stack

```bash
docker compose -f docker-compose.prod.yml --profile monitoring up -d
```

### Access Dashboards

| Service | URL | Default Credentials |
|---------|-----|---------------------|
| Grafana | http://localhost:3000 | admin / admin |
| Prometheus | http://localhost:9090 | - |
| Loki | http://localhost:3100 | - |

### Available Metrics

- `phone_agent_calls_total` - Total calls processed
- `phone_agent_call_duration_seconds` - Call duration histogram
- `phone_agent_appointments_scheduled_total` - Appointments created
- `phone_agent_sms_sent_total` - SMS messages sent
- `phone_agent_email_sent_total` - Emails sent

### Log Aggregation

All application logs are shipped to Loki via Promtail. Query logs in Grafana:

```logql
{container="itf-phone-agent"} |= "error"
```

---

## Security Hardening

### Webhook Signature Validation

Always enable signature validation in production:

```bash
ITF_TELEPHONY__WEBHOOKS__VALIDATE_SIGNATURES=true
ITF_TELEPHONY__WEBHOOKS__TIMESTAMP_TOLERANCE_SECONDS=300
```

### Network Security

1. **Use HTTPS** - Deploy with Traefik for automatic SSL
2. **Firewall** - Only expose ports 80, 443
3. **Private Network** - Use Docker network isolation

### Secrets Management

Never commit secrets to version control:

```bash
# Bad
ITF_TELEPHONY__TWILIO__AUTH_TOKEN=secret123

# Good - use Docker secrets or external secret manager
docker secret create twilio_auth_token secret.txt
```

### Database Encryption

For sensitive data at rest:

```bash
# Use PostgreSQL with encrypted storage
ITF_DATABASE__URL=postgresql+asyncpg://user:pass@db:5432/phone_agent?sslmode=require
```

---

## Troubleshooting

### Common Issues

#### Container won't start

```bash
# Check logs
docker logs itf-phone-agent

# Check resource usage
docker stats

# Verify configuration
docker exec itf-phone-agent cat /app/configs/production.yaml
```

#### Webhooks not receiving events

1. Verify domain is accessible from internet
2. Check SSL certificate is valid
3. Verify webhook URLs in provider dashboard
4. Check signature validation settings

```bash
# Test webhook endpoint
curl -X POST https://your-domain.com/api/v1/webhooks/twilio/voice \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "CallSid=test&From=+49123456789"
```

#### AI Models not loading

```bash
# Check model files exist
ls -la models/

# Verify model permissions
docker exec itf-phone-agent ls -la /app/models/

# Check STT model
docker exec itf-phone-agent python -c "from phone_agent.ai.stt import load_model; load_model()"
```

#### High memory usage

1. Reduce model size (use smaller quantization)
2. Enable model lazy loading
3. Increase swap space on Raspberry Pi

```bash
# Add swap
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

### Health Check Endpoints

```bash
# Basic health
curl http://localhost:8080/health

# Detailed health (requires auth)
curl http://localhost:8080/health/detailed

# AI model status
curl http://localhost:8080/api/v1/ai/status
```

### Support

- GitHub Issues: https://github.com/IT-Friends/phone-agent/issues
- Documentation: https://docs.itfriends.de/phone-agent
- Email: support@itfriends.de
