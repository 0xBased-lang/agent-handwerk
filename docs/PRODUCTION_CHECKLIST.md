# Production Deployment Checklist

Actionable checklist for deploying Phone Agent to production.

---

## Pre-Deployment (Day -7 to -1)

### 1. Accounts & API Keys

- [ ] **Twilio** (Voice + SMS)
  - [ ] Create account at https://www.twilio.com
  - [ ] Purchase German phone number (+49...)
  - [ ] Copy Account SID: `AC________________`
  - [ ] Copy Auth Token: `________________`
  - [ ] Note phone number: `+49________________`

- [ ] **SendGrid** (Email)
  - [ ] Create account at https://sendgrid.com
  - [ ] Verify sender domain (SPF, DKIM, DMARC)
  - [ ] Create API key (Mail Send permission)
  - [ ] Copy API Key: `SG.________________`

- [ ] **Google Calendar** (Appointments)
  - [ ] Create Google Cloud project
  - [ ] Enable Calendar API
  - [ ] Create service account
  - [ ] Download credentials JSON
  - [ ] Share practice calendar with service account email

### 2. Infrastructure

- [ ] **Domain & SSL**
  - [ ] Domain registered: `________________.de`
  - [ ] DNS A record → server IP
  - [ ] SSL certificate ready (Let's Encrypt or custom)

- [ ] **Server**
  - [ ] Raspberry Pi 5 (8GB) or cloud VM
  - [ ] Ubuntu 22.04+ or Raspberry Pi OS
  - [ ] Docker 24+ installed
  - [ ] Minimum 32GB storage
  - [ ] Static IP configured

### 3. AI Models

```bash
# Download models (run on server)
mkdir -p models/{whisper,tts}

# Whisper (German STT) - ~500MB
wget -O models/whisper/distil-whisper-large-v3-german.bin \
  https://huggingface.co/primeline/distil-whisper-large-v3-german/resolve/main/model.bin

# Piper TTS (German Thorsten) - ~60MB
wget -O models/tts/de_DE-thorsten-medium.onnx \
  https://github.com/rhasspy/piper/releases/download/v1.0.0/de_DE-thorsten-medium.onnx
```

---

## Deployment Day (Day 0)

### 4. Clone & Configure

```bash
# Clone repository
git clone https://github.com/IT-Friends/phone-agent.git
cd phone-agent

# Create environment file
cp .env.example .env
```

### 5. Fill Environment Variables

Edit `.env` with your values:

```bash
# ============================================================
# CORE
# ============================================================
ITF_ENV=production
ITF_DEBUG=false
ITF_LOG_LEVEL=INFO
ITF_SECRET_KEY=<generate-32-char-random-string>

# ============================================================
# TWILIO (Voice + SMS)
# ============================================================
ITF_TELEPHONY__TWILIO__ENABLED=true
ITF_TELEPHONY__TWILIO__ACCOUNT_SID=<your-account-sid>
ITF_TELEPHONY__TWILIO__AUTH_TOKEN=<your-auth-token>
ITF_TELEPHONY__TWILIO__FROM_NUMBER=<your-german-number>
ITF_TELEPHONY__TWILIO__WEBHOOK_URL=https://<your-domain>/api/v1/webhooks/twilio

# ============================================================
# SENDGRID (Email)
# ============================================================
ITF_INTEGRATIONS__EMAIL__ENABLED=true
ITF_INTEGRATIONS__EMAIL__PROVIDER=sendgrid
ITF_INTEGRATIONS__EMAIL__FROM_EMAIL=praxis@<your-domain>
ITF_INTEGRATIONS__EMAIL__FROM_NAME=Praxis Dr. Mustermann
ITF_INTEGRATIONS__EMAIL__SENDGRID__API_KEY=<your-api-key>

# ============================================================
# GOOGLE CALENDAR
# ============================================================
ITF_INTEGRATIONS__CALENDAR__ENABLED=true
ITF_INTEGRATIONS__CALENDAR__PROVIDER=google
ITF_INTEGRATIONS__CALENDAR__GOOGLE__CREDENTIALS_FILE=/app/configs/google-credentials.json
ITF_INTEGRATIONS__CALENDAR__GOOGLE__CALENDAR_ID=<practice-calendar-id>

# ============================================================
# DATABASE
# ============================================================
ITF_DATABASE__URL=sqlite+aiosqlite:///data/phone_agent.db
# Or for PostgreSQL:
# ITF_DATABASE__URL=postgresql+asyncpg://user:pass@localhost:5432/phone_agent

# ============================================================
# SECURITY
# ============================================================
ITF_TELEPHONY__WEBHOOKS__VALIDATE_SIGNATURES=true
ITF_TELEPHONY__WEBHOOKS__TIMESTAMP_TOLERANCE_SECONDS=300
```

### 6. Deploy

```bash
# Start services
docker compose -f docker-compose.prod.yml up -d

# Check status
docker ps

# View logs
docker logs -f itf-phone-agent
```

### 7. Configure Webhooks

**Twilio Console** (https://console.twilio.com):
- [ ] Phone Numbers → Your Number → Configure
- [ ] Voice Configuration:
  - Webhook URL: `https://<your-domain>/api/v1/webhooks/twilio/voice`
  - Method: HTTP POST
- [ ] Messaging Configuration:
  - Webhook URL: `https://<your-domain>/api/v1/webhooks/sms/twilio/incoming`
  - Method: HTTP POST

**SendGrid** (https://app.sendgrid.com):
- [ ] Settings → Mail Settings → Event Webhook
  - URL: `https://<your-domain>/api/v1/webhooks/email/sendgrid/events`
  - Events: Delivered, Opened, Clicked, Bounced, Spam Reports

---

## Verification (Day 0+1 Hour)

### 8. Health Checks

```bash
# Basic health
curl https://<your-domain>/health
# Expected: {"status": "healthy", ...}

# API health
curl https://<your-domain>/api/v1/health
# Expected: {"status": "ok", "services": {...}}

# AI models status
curl https://<your-domain>/api/v1/ai/status
# Expected: {"stt": "loaded", "tts": "loaded", "llm": "loaded"}
```

### 9. Test Call

```bash
# Make test call from your phone to the Twilio number
# Say: "Ich möchte einen Termin am Montag um 10 Uhr"
# Expected: AI responds with appointment confirmation
```

### 10. Test SMS

```bash
# Send test SMS to the Twilio number
# Text: "Termin bestätigen"
# Expected: Confirmation SMS reply
```

### 11. Test Email

```bash
# Trigger appointment confirmation
curl -X POST https://<your-domain>/api/v1/test/email \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "type": "confirmation"}'
```

---

## Post-Deployment (Day 1-7)

### 12. Monitoring Setup

- [ ] Enable Grafana dashboards
  ```bash
  docker compose -f docker-compose.prod.yml --profile monitoring up -d
  ```
- [ ] Access Grafana: `https://<your-domain>:3000`
- [ ] Import Phone Agent dashboard
- [ ] Configure alerts for:
  - [ ] High error rate (>5%)
  - [ ] Long call queue (>10 calls)
  - [ ] Low disk space (<20%)
  - [ ] AI model failures

### 13. Backup Configuration

```bash
# Create backup script
cat > /opt/backup-phone-agent.sh << 'EOF'
#!/bin/bash
DATE=$(date +%Y%m%d)
BACKUP_DIR=/backup/phone-agent

# Backup database
docker exec itf-phone-agent-db pg_dump -U phone_agent > $BACKUP_DIR/db_$DATE.sql

# Backup config
cp -r /opt/phone-agent/.env $BACKUP_DIR/env_$DATE

# Backup recordings
tar -czf $BACKUP_DIR/recordings_$DATE.tar.gz /opt/phone-agent/data/recordings/

# Retain 30 days
find $BACKUP_DIR -mtime +30 -delete
EOF

chmod +x /opt/backup-phone-agent.sh

# Add to cron (daily at 2am)
echo "0 2 * * * /opt/backup-phone-agent.sh" | crontab -
```

### 14. Security Review

- [ ] Firewall configured (only 80, 443 open)
- [ ] SSH key-only authentication
- [ ] Fail2ban installed and configured
- [ ] Secrets not in version control
- [ ] HTTPS enforced (redirect HTTP → HTTPS)
- [ ] Webhook signatures validated
- [ ] Database connection encrypted

### 15. Documentation

- [ ] Practice staff trained on monitoring dashboard
- [ ] Emergency contact procedures documented
- [ ] Rollback procedure tested

---

## Industry-Specific Configuration

### Healthcare (Gesundheit)

```bash
# Additional environment variables
ITF_INDUSTRY=gesundheit
ITF_INDUSTRY__GESUNDHEIT__ENABLE_EMERGENCY_DETECTION=true
ITF_INDUSTRY__GESUNDHEIT__EMERGENCY_PHRASES="brustschmerzen,atemnot,bewusstlos,112"
ITF_INDUSTRY__GESUNDHEIT__TRIAGE_ENABLED=true
```

### Trades (Handwerk)

```bash
ITF_INDUSTRY=handwerk
ITF_INDUSTRY__HANDWERK__EMERGENCY_SERVICES="gas,wasser,strom"
ITF_INDUSTRY__HANDWERK__DISPATCH_ENABLED=true
```

### Hospitality (Gastro)

```bash
ITF_INDUSTRY=gastro
ITF_INDUSTRY__GASTRO__TABLE_COUNT=20
ITF_INDUSTRY__GASTRO__ENABLE_NO_SHOW_DETECTION=true
ITF_INDUSTRY__GASTRO__REMINDER_HOURS_BEFORE=24
```

### Professional Services (Freie Berufe)

```bash
ITF_INDUSTRY=freie_berufe
ITF_INDUSTRY__FREIE_BERUFE__LEAD_SCORING_ENABLED=true
ITF_INDUSTRY__FREIE_BERUFE__SERVICE_AREAS="legal,tax,consulting"
```

---

## Quick Reference

### Important URLs

| Service | URL |
|---------|-----|
| Health Check | `https://<domain>/health` |
| API Docs | `https://<domain>/api/v1/docs` |
| Grafana | `https://<domain>:3000` |
| Twilio Console | https://console.twilio.com |
| SendGrid Dashboard | https://app.sendgrid.com |

### Emergency Commands

```bash
# Restart service
docker compose restart phone-agent

# View recent errors
docker logs itf-phone-agent --since 1h | grep -i error

# Check disk space
df -h

# Check memory
free -m

# Stop all calls (emergency)
curl -X POST https://<domain>/api/v1/admin/emergency-stop
```

### Support Contacts

- Technical Issues: support@itfriends.de
- Twilio Support: https://support.twilio.com
- SendGrid Support: https://support.sendgrid.com

---

## Checklist Summary

| Phase | Items | Completed |
|-------|-------|-----------|
| Pre-Deployment | 12 items | [ ] |
| Deployment Day | 7 items | [ ] |
| Verification | 4 items | [ ] |
| Post-Deployment | 4 items | [ ] |

**Total: 27 items**

---

*Last updated: December 2024*
