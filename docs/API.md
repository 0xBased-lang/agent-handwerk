# IT-Friends Phone Agent API Reference

Complete API documentation for the Phone Agent REST API.

**Base URL**: `http://localhost:8080/api/v1`

**OpenAPI**: Available at `/docs` (debug mode) or export from `/openapi.json`

---

## Table of Contents

1. [Authentication](#authentication)
2. [Health Check](#health-check)
3. [Calls](#calls)
4. [Appointments](#appointments)
5. [Triage](#triage)
6. [Recall Campaigns](#recall-campaigns)
7. [Outbound Calling](#outbound-calling)
8. [CRM](#crm)
9. [Analytics](#analytics)
10. [Compliance](#compliance)
11. [Webhooks](#webhooks)
12. [Error Handling](#error-handling)

---

## Authentication

Currently, the API uses device-based authentication via the `device_id` configuration. For production deployments, consider adding:

- API key authentication
- JWT tokens
- OAuth 2.0

```yaml
# Future authentication header
Authorization: Bearer <token>
X-Device-ID: pi-12345678
```

---

## Health Check

### GET /health

Basic health check endpoint.

**Response**:
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "environment": "production",
  "device_id": "pi-12345678"
}
```

### GET /health/detailed

Detailed health check including AI models and database.

**Response**:
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "components": {
    "database": "healthy",
    "stt": "ready",
    "llm": "ready",
    "tts": "ready"
  },
  "uptime_seconds": 3600,
  "memory_mb": 2800
}
```

---

## Calls

### GET /api/v1/calls

List all calls with pagination.

**Query Parameters**:
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | int | 50 | Max results |
| `offset` | int | 0 | Pagination offset |
| `status` | string | - | Filter by status |
| `from_date` | date | - | Filter by date |

**Response**:
```json
{
  "calls": [
    {
      "id": "uuid",
      "caller_number": "+49123456789",
      "status": "completed",
      "duration_seconds": 120,
      "industry": "gesundheit",
      "triage_result": "normal",
      "created_at": "2024-12-01T10:00:00Z"
    }
  ],
  "total": 100,
  "limit": 50,
  "offset": 0
}
```

### GET /api/v1/calls/{call_id}

Get call details.

**Response**:
```json
{
  "id": "uuid",
  "caller_number": "+49123456789",
  "status": "completed",
  "duration_seconds": 120,
  "industry": "gesundheit",
  "triage_result": "normal",
  "appointment_id": "uuid",
  "transcript": "...",
  "created_at": "2024-12-01T10:00:00Z",
  "ended_at": "2024-12-01T10:02:00Z"
}
```

### POST /api/v1/calls

Initiate an outbound call.

**Request**:
```json
{
  "to_number": "+49123456789",
  "campaign_id": "uuid",
  "message_template": "recall_reminder"
}
```

**Response**:
```json
{
  "call_id": "uuid",
  "status": "initiated"
}
```

---

## Appointments

### GET /api/v1/appointments

List appointments.

**Query Parameters**:
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `date` | date | today | Filter by date |
| `status` | string | - | Filter by status |
| `patient_id` | uuid | - | Filter by patient |

**Response**:
```json
{
  "appointments": [
    {
      "id": "uuid",
      "patient_id": "uuid",
      "patient_name": "Max Mustermann",
      "datetime": "2024-12-01T14:30:00",
      "duration_minutes": 15,
      "type": "consultation",
      "status": "confirmed",
      "notes": "Folgeuntersuchung"
    }
  ]
}
```

### POST /api/v1/appointments

Create a new appointment.

**Request**:
```json
{
  "patient_id": "uuid",
  "datetime": "2024-12-01T14:30:00",
  "duration_minutes": 15,
  "type": "consultation",
  "notes": "Ersttermin",
  "send_confirmation": true
}
```

### GET /api/v1/appointments/slots

Get available time slots.

**Query Parameters**:
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `date` | date | today | Date to check |
| `duration` | int | 15 | Slot duration |
| `type` | string | - | Appointment type |

**Response**:
```json
{
  "date": "2024-12-01",
  "slots": [
    {"start": "08:00", "end": "08:15", "available": true},
    {"start": "08:15", "end": "08:30", "available": false},
    {"start": "08:30", "end": "08:45", "available": true}
  ]
}
```

### PATCH /api/v1/appointments/{id}

Update appointment.

**Request**:
```json
{
  "status": "cancelled",
  "cancellation_reason": "Patient called to cancel"
}
```

---

## Triage

### POST /api/v1/triage/assess

Perform symptom-based triage assessment.

**Request**:
```json
{
  "symptoms": ["Brustschmerzen", "Atemnot"],
  "duration": "seit 2 Stunden",
  "severity": "stark",
  "patient_context": {
    "age": 65,
    "known_conditions": ["Diabetes", "Bluthochdruck"]
  }
}
```

**Response**:
```json
{
  "urgency_level": "akut",
  "recommended_action": "transfer_emergency",
  "reasoning": "Brustschmerzen mit Atemnot bei Risikopatienten erfordern sofortige Abklärung",
  "emergency_symptoms_detected": ["chest_pain", "breathing_difficulty"],
  "suggested_response": "Bitte rufen Sie sofort den Notruf 112 an."
}
```

### GET /api/v1/triage/levels

Get configured triage urgency levels.

**Response**:
```json
{
  "levels": [
    {
      "name": "akut",
      "description": "Sofortige medizinische Hilfe nötig",
      "action": "transfer_emergency",
      "color": "red"
    },
    {
      "name": "dringend",
      "description": "Termin heute erforderlich",
      "action": "schedule_same_day",
      "color": "orange"
    }
  ]
}
```

---

## Recall Campaigns

### GET /api/v1/recall/campaigns

List recall campaigns.

**Response**:
```json
{
  "campaigns": [
    {
      "id": "uuid",
      "name": "Impferinnerung Q1",
      "type": "vaccination",
      "status": "active",
      "target_count": 150,
      "contacted_count": 45,
      "success_count": 38,
      "created_at": "2024-01-01T00:00:00Z"
    }
  ]
}
```

### POST /api/v1/recall/campaigns

Create a recall campaign.

**Request**:
```json
{
  "name": "Vorsorgeuntersuchung 2025",
  "type": "preventive",
  "patient_filter": {
    "last_checkup_before": "2024-01-01",
    "age_min": 35
  },
  "message_template": "preventive_reminder",
  "channels": ["phone", "sms"],
  "schedule": {
    "start_date": "2025-01-15",
    "daily_limit": 50,
    "call_hours": {"start": "09:00", "end": "17:00"}
  }
}
```

### GET /api/v1/recall/campaigns/{id}/patients

Get patients in campaign.

### POST /api/v1/recall/campaigns/{id}/start

Start campaign execution.

### POST /api/v1/recall/campaigns/{id}/pause

Pause campaign execution.

---

## Outbound Calling

### POST /api/v1/outbound/call

Initiate an outbound call.

**Request**:
```json
{
  "to_number": "+49123456789",
  "script_type": "recall_reminder",
  "patient_id": "uuid",
  "campaign_id": "uuid",
  "metadata": {
    "appointment_type": "vaccination",
    "last_visit": "2024-06-15"
  }
}
```

### GET /api/v1/outbound/queue

Get pending outbound calls.

### DELETE /api/v1/outbound/queue/{id}

Cancel a pending outbound call.

---

## CRM

### GET /api/v1/crm/contacts

List contacts.

**Query Parameters**:
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `search` | string | - | Search term |
| `limit` | int | 50 | Max results |

### POST /api/v1/crm/contacts

Create a contact.

**Request**:
```json
{
  "first_name": "Max",
  "last_name": "Mustermann",
  "phone": "+49123456789",
  "email": "max@example.de",
  "birth_date": "1980-05-15"
}
```

### GET /api/v1/crm/contacts/{id}

Get contact details.

### PATCH /api/v1/crm/contacts/{id}

Update contact.

### DELETE /api/v1/crm/contacts/{id}

Delete contact (soft delete).

### GET /api/v1/crm/companies

List companies.

### POST /api/v1/crm/companies

Create a company.

---

## Analytics

### GET /api/v1/analytics/dashboard

Get dashboard summary.

**Response**:
```json
{
  "today": {
    "calls_total": 45,
    "calls_completed": 42,
    "appointments_scheduled": 18,
    "average_call_duration": 95
  },
  "week": {
    "calls_total": 280,
    "appointments_scheduled": 95
  },
  "trends": {
    "calls_vs_last_week": "+12%",
    "appointments_vs_last_week": "+8%"
  }
}
```

### GET /api/v1/analytics/calls

Get call analytics.

**Query Parameters**:
| Parameter | Type | Description |
|-----------|------|-------------|
| `start_date` | date | Start of range |
| `end_date` | date | End of range |
| `group_by` | string | day, week, month |

### GET /api/v1/analytics/triage

Get triage analytics (urgency distribution).

### GET /api/v1/analytics/campaigns

Get campaign performance analytics.

---

## Compliance

### GET /api/v1/compliance/consent/{patient_id}

Get patient consent records.

**Response**:
```json
{
  "patient_id": "uuid",
  "consents": [
    {
      "type": "call_recording",
      "granted": true,
      "granted_at": "2024-01-15T10:00:00Z",
      "method": "verbal",
      "expires_at": null
    },
    {
      "type": "appointment_reminders",
      "granted": true,
      "granted_at": "2024-01-15T10:00:00Z"
    }
  ]
}
```

### POST /api/v1/compliance/consent/{patient_id}

Grant consent.

**Request**:
```json
{
  "consent_type": "call_recording",
  "method": "verbal",
  "call_id": "uuid"
}
```

### DELETE /api/v1/compliance/consent/{patient_id}/{type}

Revoke consent.

### GET /api/v1/compliance/audit

Query audit logs.

**Query Parameters**:
| Parameter | Type | Description |
|-----------|------|-------------|
| `entity_type` | string | patient, call, appointment |
| `entity_id` | uuid | Specific entity |
| `action` | string | data_read, data_created, etc. |
| `start_date` | date | Start of range |
| `end_date` | date | End of range |

### GET /api/v1/compliance/audit/integrity

Verify audit log integrity (checksums).

### GET /api/v1/compliance/export/{patient_id}

Export all patient data (DSGVO data portability).

**Response**: ZIP file with JSON data

### DELETE /api/v1/compliance/erasure/{patient_id}

Request data erasure (DSGVO right to erasure).

---

## Webhooks

### Provider Webhooks (Inbound)

#### POST /api/v1/webhooks/twilio/voice

Twilio voice webhook for incoming calls.

#### POST /api/v1/webhooks/twilio/status

Twilio call status updates.

#### POST /api/v1/webhooks/sipgate/call

sipgate call webhook.

### SMS Webhooks

#### POST /api/v1/webhooks/sms/twilio/status

Twilio SMS delivery status.

**Payload** (from Twilio):
```
MessageSid=SM...
MessageStatus=delivered
To=+49123456789
```

#### POST /api/v1/webhooks/sms/twilio/inbound

Inbound SMS handling.

#### GET /api/v1/webhooks/sms/stats/today

Today's SMS statistics.

### Email Webhooks

#### POST /api/v1/webhooks/email/sendgrid/events

SendGrid email events (delivered, opened, clicked, bounced).

**Payload** (from SendGrid):
```json
[
  {
    "email": "patient@example.de",
    "event": "delivered",
    "timestamp": 1701432000,
    "sg_message_id": "..."
  }
]
```

#### GET /api/v1/webhooks/email/stats/today

Today's email statistics.

#### GET /api/v1/webhooks/email/stats/range

Email statistics for date range.

---

## Error Handling

All errors follow a consistent format:

```json
{
  "detail": "Human-readable error message",
  "error_code": "VALIDATION_ERROR",
  "field": "phone_number"
}
```

### HTTP Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 201 | Created |
| 400 | Bad Request (validation error) |
| 401 | Unauthorized |
| 403 | Forbidden |
| 404 | Not Found |
| 422 | Unprocessable Entity |
| 500 | Internal Server Error |

### Common Error Codes

| Code | Description |
|------|-------------|
| `VALIDATION_ERROR` | Invalid request data |
| `NOT_FOUND` | Resource not found |
| `DUPLICATE_ENTRY` | Resource already exists |
| `CONSENT_REQUIRED` | Missing patient consent |
| `CAPACITY_EXCEEDED` | No available slots |
| `PROVIDER_ERROR` | External provider failed |

---

## Rate Limiting

Currently no rate limiting. For production, consider:

```yaml
rate_limits:
  default: 100/minute
  webhooks: 1000/minute
  analytics: 10/minute
```

---

## Webhook Signature Validation

### Twilio

```python
from twilio.request_validator import RequestValidator

validator = RequestValidator(auth_token)
if not validator.validate(url, params, signature):
    raise HTTPException(403, "Invalid signature")
```

### SendGrid

SendGrid uses timestamp + signature headers:
- `X-Twilio-Email-Event-Webhook-Signature`
- `X-Twilio-Email-Event-Webhook-Timestamp`

---

## WebSocket Endpoints

### /api/v1/ws/audio

Real-time bidirectional audio streaming for web-based testing.

**Connection**:
```javascript
const ws = new WebSocket('ws://localhost:8080/api/v1/ws/audio');
ws.binaryType = 'arraybuffer';
```

**Message Types**:
- Client → Server: Raw audio (16kHz, 16-bit PCM)
- Server → Client: TTS audio response

---

## SDK Examples

### Python

```python
import httpx

client = httpx.Client(base_url="http://localhost:8080/api/v1")

# Get appointments
response = client.get("/appointments", params={"date": "2024-12-01"})
appointments = response.json()

# Create appointment
response = client.post("/appointments", json={
    "patient_id": "uuid",
    "datetime": "2024-12-01T14:30:00",
    "type": "consultation"
})
```

### cURL

```bash
# Health check
curl http://localhost:8080/health

# List calls
curl "http://localhost:8080/api/v1/calls?limit=10"

# Triage assessment
curl -X POST http://localhost:8080/api/v1/triage/assess \
  -H "Content-Type: application/json" \
  -d '{"symptoms": ["Kopfschmerzen"], "severity": "mittel"}'
```

---

*Generated: December 2024*
*Version: 0.1.0*
