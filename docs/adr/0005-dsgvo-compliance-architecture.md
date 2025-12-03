# ADR 0005: DSGVO Compliance Architecture

## Status

Accepted

## Date

2024-12-01

## Context

German healthcare practices and businesses are subject to strict DSGVO (GDPR) requirements. Healthcare data specifically falls under Article 9 "special categories" requiring additional protections.

### Regulatory Requirements

1. **DSGVO (GDPR)**: EU-wide data protection regulation
2. **BDSG**: German Federal Data Protection Act
3. **SGB V §291a**: Social Code Book V (healthcare-specific)
4. **KDG/DSG-EKD**: Church data protection laws (for church-affiliated practices)

### Key Compliance Challenges

- **Consent Management**: Must obtain explicit consent before processing
- **Data Minimization**: Collect only necessary data
- **Purpose Limitation**: Use data only for stated purposes
- **Storage Limitation**: Delete data after retention period
- **Audit Trail**: Log all data access and modifications
- **Data Portability**: Export patient data on request
- **Right to Erasure**: Delete data on patient request

## Decision

We implemented a **comprehensive compliance framework** as a first-class architectural component.

### Architecture Components

```
┌─────────────────────────────────────────────────────────┐
│                   Compliance Framework                   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │
│  │   Consent   │  │    Audit    │  │    Data     │     │
│  │   Manager   │  │   Logger    │  │ Protection  │     │
│  └─────────────┘  └─────────────┘  └─────────────┘     │
│         │                │                │             │
│         └────────────────┼────────────────┘             │
│                          ↓                              │
│              ┌─────────────────────┐                   │
│              │   Compliance API    │                   │
│              └─────────────────────┘                   │
└─────────────────────────────────────────────────────────┘
```

### Consent Manager

```python
class ConsentManager:
    """Manages patient consent for data processing."""

    async def request_consent(
        self,
        patient_id: str,
        consent_types: list[ConsentType],
    ) -> ConsentResult:
        """Request consent during call, log response."""

    async def verify_consent(
        self,
        patient_id: str,
        consent_type: ConsentType,
    ) -> bool:
        """Check if valid consent exists."""

    async def revoke_consent(
        self,
        patient_id: str,
        consent_type: ConsentType,
    ) -> None:
        """Revoke consent (right to withdraw)."""

class ConsentType(Enum):
    CALL_RECORDING = "call_recording"
    DATA_PROCESSING = "data_processing"
    APPOINTMENT_REMINDERS = "appointment_reminders"
    RECALL_CAMPAIGNS = "recall_campaigns"
    THIRD_PARTY_SHARING = "third_party_sharing"
```

### Audit Logger

```python
class AuditLogger:
    """Immutable audit trail for all data operations."""

    async def log(
        self,
        action: AuditAction,
        actor: str,  # "system" or user identifier
        entity_type: str,
        entity_id: str,
        details: dict,
    ) -> None:
        """Log action with timestamp, never modifiable."""

class AuditAction(Enum):
    # Data access
    DATA_READ = "data_read"
    DATA_CREATED = "data_created"
    DATA_UPDATED = "data_updated"
    DATA_DELETED = "data_deleted"

    # Consent
    CONSENT_GRANTED = "consent_granted"
    CONSENT_REVOKED = "consent_revoked"

    # Communication
    CALL_STARTED = "call_started"
    CALL_ENDED = "call_ended"
    SMS_SENT = "sms_sent"
    EMAIL_SENT = "email_sent"

    # System
    EXPORT_REQUESTED = "export_requested"
    ERASURE_REQUESTED = "erasure_requested"
```

### Data Protection Service

```python
class DataProtectionService:
    """Handles data retention, export, and erasure."""

    async def apply_retention_policy(self) -> int:
        """Delete data past retention period, return count."""

    async def export_patient_data(
        self,
        patient_id: str,
    ) -> PatientDataExport:
        """Export all patient data (portability)."""

    async def erase_patient_data(
        self,
        patient_id: str,
    ) -> ErasureResult:
        """Delete all patient data (right to erasure)."""
```

### Database Schema

```sql
-- Consent records
CREATE TABLE consents (
    id UUID PRIMARY KEY,
    patient_id UUID NOT NULL,
    consent_type VARCHAR(50) NOT NULL,
    granted_at TIMESTAMP NOT NULL,
    revoked_at TIMESTAMP,
    expires_at TIMESTAMP,
    method VARCHAR(20),  -- 'verbal', 'written', 'digital'
    call_id UUID,  -- Link to call where consent given
    UNIQUE (patient_id, consent_type)
);

-- Audit log (append-only)
CREATE TABLE audit_log (
    id UUID PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    action VARCHAR(50) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    entity_id UUID,
    details JSONB,
    checksum VARCHAR(64)  -- SHA-256 for integrity
);

-- Indexes for compliance queries
CREATE INDEX idx_audit_timestamp ON audit_log(timestamp);
CREATE INDEX idx_audit_entity ON audit_log(entity_type, entity_id);
```

### Retention Policies

```yaml
# configs/production.yaml
compliance:
  retention:
    call_recordings: 90     # days
    appointment_data: 365   # days
    audit_logs: 730        # 2 years (legal requirement)
    contact_data: 365      # days after last interaction
```

### Call Flow with Consent

```
1. Call answered
2. AI: "Diese Aufnahme dient der Qualitätssicherung.
        Sind Sie damit einverstanden?"
        (This recording is for quality assurance. Do you agree?)
3. If "Ja" -> ConsentManager.grant(CALL_RECORDING)
   If "Nein" -> Recording disabled, call continues
4. AI: "Ich verarbeite Ihre Daten zur Terminvereinbarung.
        Einverstanden?"
        (I process your data for appointment scheduling. Agreed?)
5. If "Ja" -> ConsentManager.grant(DATA_PROCESSING)
6. Proceed with scheduling (all actions logged)
7. Call ends -> AuditLogger.log(CALL_ENDED)
```

## Consequences

### Positive

1. **Legal Compliance**: Documented DSGVO compliance
2. **Patient Trust**: Transparent consent handling
3. **Audit Ready**: Complete trail for regulatory inspections
4. **Data Control**: Patients can export/delete their data
5. **Local Processing**: No third-party data sharing

### Negative

1. **User Experience**: Consent prompts add call duration
2. **Complexity**: Additional code paths for consent states
3. **Storage**: Audit logs grow continuously
4. **Development Cost**: Compliance features take time

### Trade-offs Accepted

- Slightly longer calls for explicit consent (required by law)
- Audit log storage costs (necessary for compliance)
- Code complexity (justified by regulatory requirements)

## API Endpoints

```
# Consent management
POST /api/v1/compliance/consent/{patient_id}
GET  /api/v1/compliance/consent/{patient_id}
DELETE /api/v1/compliance/consent/{patient_id}/{type}

# Data portability
GET /api/v1/compliance/export/{patient_id}

# Right to erasure
DELETE /api/v1/compliance/erasure/{patient_id}

# Audit logs
GET /api/v1/compliance/audit
GET /api/v1/compliance/audit/integrity  # Checksum verification
```

## Testing

```python
# tests/test_compliance_api.py
async def test_consent_granted_and_logged():
    # Grant consent
    await consent_manager.grant(patient_id, ConsentType.CALL_RECORDING)

    # Verify consent exists
    assert await consent_manager.verify(patient_id, ConsentType.CALL_RECORDING)

    # Verify audit log entry
    logs = await audit_logger.get_for_entity("patient", patient_id)
    assert any(l.action == AuditAction.CONSENT_GRANTED for l in logs)
```

## Related Decisions

- [ADR 0001: Local-First Edge Architecture](./0001-local-first-edge-architecture.md)
- [ADR 0002: Industry Module Pattern](./0002-industry-module-pattern.md)
