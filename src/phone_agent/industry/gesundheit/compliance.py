"""Healthcare compliance and data protection (DSGVO/GDPR).

German healthcare-specific compliance including:
- DSGVO (GDPR) data protection
- Medical confidentiality (Schweigepflicht)
- Patient consent management
- Audit logging
- Data retention policies
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from enum import Enum
from typing import Any, Callable
from uuid import UUID, uuid4
import hashlib
import json


class ConsentType(str, Enum):
    """Types of patient consent."""

    TREATMENT = "treatment"                 # Behandlungsvertrag
    DATA_PROCESSING = "data_processing"     # Datenverarbeitung
    PHONE_CONTACT = "phone_contact"         # Telefonische Kontaktaufnahme
    SMS_CONTACT = "sms_contact"             # SMS-Benachrichtigungen
    EMAIL_CONTACT = "email_contact"         # E-Mail-Kommunikation
    DATA_SHARING = "data_sharing"           # Datenweitergabe
    RESEARCH = "research"                   # Forschungszwecke
    MARKETING = "marketing"                 # Marketingzwecke (selten in Praxen)
    VOICE_RECORDING = "voice_recording"     # Gesprächsaufzeichnung
    AI_PROCESSING = "ai_processing"         # KI-Verarbeitung


class ConsentStatus(str, Enum):
    """Status of consent."""

    GRANTED = "granted"
    DENIED = "denied"
    WITHDRAWN = "withdrawn"
    EXPIRED = "expired"
    PENDING = "pending"


class AuditAction(str, Enum):
    """Types of auditable actions."""

    # Data access
    DATA_VIEW = "data_view"
    DATA_EXPORT = "data_export"
    DATA_SEARCH = "data_search"

    # Data modification
    DATA_CREATE = "data_create"
    DATA_UPDATE = "data_update"
    DATA_DELETE = "data_delete"

    # Communication
    CALL_STARTED = "call_started"
    CALL_ENDED = "call_ended"
    SMS_SENT = "sms_sent"
    EMAIL_SENT = "email_sent"

    # Consent
    CONSENT_GRANTED = "consent_granted"
    CONSENT_DENIED = "consent_denied"
    CONSENT_WITHDRAWN = "consent_withdrawn"

    # Appointments
    APPOINTMENT_CREATED = "appointment_created"
    APPOINTMENT_CANCELLED = "appointment_cancelled"
    APPOINTMENT_MODIFIED = "appointment_modified"

    # System
    LOGIN = "login"
    LOGOUT = "logout"
    CONFIG_CHANGE = "config_change"


@dataclass
class Consent:
    """Patient consent record."""

    id: UUID
    patient_id: UUID
    consent_type: ConsentType
    status: ConsentStatus
    granted_at: datetime | None = None
    expires_at: datetime | None = None
    withdrawn_at: datetime | None = None
    granted_by: str | None = None  # How consent was obtained
    notes: str | None = None
    version: str = "1.0"  # Consent form version

    def is_valid(self) -> bool:
        """Check if consent is currently valid."""
        if self.status != ConsentStatus.GRANTED:
            return False

        if self.expires_at and datetime.now() > self.expires_at:
            return False

        return True

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "patient_id": str(self.patient_id),
            "consent_type": self.consent_type.value,
            "status": self.status.value,
            "granted_at": self.granted_at.isoformat() if self.granted_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "withdrawn_at": self.withdrawn_at.isoformat() if self.withdrawn_at else None,
            "granted_by": self.granted_by,
            "notes": self.notes,
            "version": self.version,
            "is_valid": self.is_valid(),
        }


@dataclass
class AuditLogEntry:
    """Audit log entry for compliance tracking."""

    id: UUID
    timestamp: datetime
    action: AuditAction
    actor_id: str  # User or system ID
    actor_type: str  # "user", "system", "ai_agent"
    resource_type: str  # "patient", "appointment", etc.
    resource_id: str | None = None
    patient_id: UUID | None = None
    details: dict[str, Any] = field(default_factory=dict)
    ip_address: str | None = None
    user_agent: str | None = None
    session_id: str | None = None

    # Data integrity
    checksum: str | None = None

    def calculate_checksum(self) -> str:
        """Calculate checksum for tamper detection."""
        data = f"{self.id}{self.timestamp}{self.action}{self.actor_id}{self.resource_id}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "timestamp": self.timestamp.isoformat(),
            "action": self.action.value,
            "actor_id": self.actor_id,
            "actor_type": self.actor_type,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "patient_id": str(self.patient_id) if self.patient_id else None,
            "details": self.details,
            "ip_address": self.ip_address,
            "checksum": self.checksum,
        }


@dataclass
class DataRetentionPolicy:
    """Data retention policy configuration."""

    resource_type: str
    retention_days: int
    archive_after_days: int | None = None
    legal_basis: str = ""
    description: str = ""


# German healthcare data retention requirements
DEFAULT_RETENTION_POLICIES: list[DataRetentionPolicy] = [
    DataRetentionPolicy(
        resource_type="medical_records",
        retention_days=10 * 365,  # 10 years after last treatment
        legal_basis="§ 10 MBO-Ä, § 630f BGB",
        description="Patientenakten müssen 10 Jahre aufbewahrt werden",
    ),
    DataRetentionPolicy(
        resource_type="appointment_records",
        retention_days=10 * 365,
        legal_basis="§ 630f BGB",
        description="Terminaufzeichnungen als Teil der Behandlungsdokumentation",
    ),
    DataRetentionPolicy(
        resource_type="call_recordings",
        retention_days=365,  # 1 year
        archive_after_days=30,
        legal_basis="Art. 6 DSGVO - Berechtigtes Interesse",
        description="Anrufaufzeichnungen zur Qualitätssicherung",
    ),
    DataRetentionPolicy(
        resource_type="consent_records",
        retention_days=10 * 365 + 365,  # Retention + 1 year
        legal_basis="Art. 7 DSGVO - Nachweispflicht",
        description="Einwilligungsnachweise",
    ),
    DataRetentionPolicy(
        resource_type="audit_logs",
        retention_days=5 * 365,  # 5 years
        legal_basis="Art. 5, 30 DSGVO",
        description="Verarbeitungsprotokolle",
    ),
]


# German consent text templates
CONSENT_TEXTS: dict[ConsentType, str] = {
    ConsentType.PHONE_CONTACT: """
Einwilligung zur telefonischen Kontaktaufnahme

Ich willige ein, dass die Praxis mich zu folgenden Zwecken telefonisch kontaktieren darf:
- Terminerinnerungen
- Terminvereinbarungen
- Wichtige medizinische Mitteilungen
- Recall-Aktionen (z.B. Vorsorge, Impfungen)

Diese Einwilligung kann ich jederzeit widerrufen.
""",
    ConsentType.SMS_CONTACT: """
Einwilligung zu SMS-Benachrichtigungen

Ich willige ein, dass die Praxis mir SMS-Nachrichten zu folgenden Zwecken senden darf:
- Terminerinnerungen
- Terminbestätigungen
- Wichtige Praxismitteilungen

Diese Einwilligung kann ich jederzeit widerrufen.
""",
    ConsentType.AI_PROCESSING: """
Einwilligung zur KI-gestützten Kommunikation

Ich willige ein, dass meine Anrufe von einem KI-gestützten Telefonassistenten
entgegengenommen und bearbeitet werden dürfen. Der Assistent kann:
- Termine vereinbaren und ändern
- Allgemeine Anfragen beantworten
- Bei dringenden Anliegen an die Praxis weiterleiten

Die Gespräche werden nicht dauerhaft gespeichert, es sei denn, ich willige
gesondert in die Aufzeichnung ein.

Diese Einwilligung kann ich jederzeit widerrufen.
""",
    ConsentType.VOICE_RECORDING: """
Einwilligung zur Gesprächsaufzeichnung

Ich willige ein, dass meine Telefongespräche mit der Praxis aufgezeichnet werden dürfen.
Die Aufzeichnungen dienen:
- Der Qualitätssicherung
- Der Dokumentation von Terminvereinbarungen
- Der Verbesserung des Services

Die Aufzeichnungen werden gemäß den geltenden Datenschutzbestimmungen gespeichert
und nach spätestens einem Jahr gelöscht.

Diese Einwilligung kann ich jederzeit widerrufen.
""",
}


class ConsentManager:
    """Manager for patient consent."""

    def __init__(self):
        """Initialize consent manager."""
        self._consents: dict[UUID, Consent] = {}
        self._consent_texts = CONSENT_TEXTS

    def grant_consent(
        self,
        patient_id: UUID,
        consent_type: ConsentType,
        granted_by: str = "phone_agent",
        duration_days: int | None = None,
        notes: str | None = None,
    ) -> Consent:
        """
        Record patient consent.

        Args:
            patient_id: ID of the patient
            consent_type: Type of consent
            granted_by: How consent was obtained
            duration_days: Optional consent duration
            notes: Additional notes

        Returns:
            Created consent record
        """
        consent = Consent(
            id=uuid4(),
            patient_id=patient_id,
            consent_type=consent_type,
            status=ConsentStatus.GRANTED,
            granted_at=datetime.now(),
            expires_at=datetime.now() + timedelta(days=duration_days) if duration_days else None,
            granted_by=granted_by,
            notes=notes,
        )

        self._consents[consent.id] = consent
        return consent

    def withdraw_consent(
        self,
        patient_id: UUID,
        consent_type: ConsentType,
        notes: str | None = None,
    ) -> Consent | None:
        """
        Withdraw patient consent.

        Args:
            patient_id: ID of the patient
            consent_type: Type of consent to withdraw

        Returns:
            Updated consent record or None
        """
        for consent in self._consents.values():
            if (
                consent.patient_id == patient_id
                and consent.consent_type == consent_type
                and consent.status == ConsentStatus.GRANTED
            ):
                consent.status = ConsentStatus.WITHDRAWN
                consent.withdrawn_at = datetime.now()
                consent.notes = notes or consent.notes
                return consent

        return None

    def check_consent(
        self,
        patient_id: UUID,
        consent_type: ConsentType,
    ) -> bool:
        """
        Check if patient has valid consent.

        Args:
            patient_id: ID of the patient
            consent_type: Type of consent to check

        Returns:
            True if valid consent exists
        """
        for consent in self._consents.values():
            if (
                consent.patient_id == patient_id
                and consent.consent_type == consent_type
                and consent.is_valid()
            ):
                return True

        return False

    def get_patient_consents(self, patient_id: UUID) -> list[Consent]:
        """Get all consents for a patient."""
        return [
            c for c in self._consents.values()
            if c.patient_id == patient_id
        ]

    def get_consent_text(
        self,
        consent_type: ConsentType,
        language: str = "de",
    ) -> str:
        """Get consent text for display/reading."""
        return self._consent_texts.get(consent_type, "")

    def get_required_consents_for_call(self) -> list[ConsentType]:
        """Get list of consents required for AI phone calls."""
        return [
            ConsentType.PHONE_CONTACT,
            ConsentType.AI_PROCESSING,
        ]


class AuditLogger:
    """Audit logging for compliance."""

    def __init__(self, storage_callback: Callable[[AuditLogEntry], None] | None = None):
        """Initialize audit logger."""
        self._logs: list[AuditLogEntry] = []
        self._storage_callback = storage_callback

    def log(
        self,
        action: AuditAction,
        actor_id: str,
        actor_type: str,
        resource_type: str,
        resource_id: str | None = None,
        patient_id: UUID | None = None,
        details: dict[str, Any] | None = None,
        ip_address: str | None = None,
        session_id: str | None = None,
    ) -> AuditLogEntry:
        """
        Log an auditable action.

        Args:
            action: Type of action
            actor_id: ID of the actor (user, system)
            actor_type: Type of actor
            resource_type: Type of resource affected
            resource_id: ID of the resource
            patient_id: ID of related patient
            details: Additional details
            ip_address: IP address of actor
            session_id: Session identifier

        Returns:
            Created log entry
        """
        entry = AuditLogEntry(
            id=uuid4(),
            timestamp=datetime.now(),
            action=action,
            actor_id=actor_id,
            actor_type=actor_type,
            resource_type=resource_type,
            resource_id=resource_id,
            patient_id=patient_id,
            details=details or {},
            ip_address=ip_address,
            session_id=session_id,
        )

        # Calculate checksum for integrity
        entry.checksum = entry.calculate_checksum()

        # Store locally
        self._logs.append(entry)

        # Call external storage if configured
        if self._storage_callback:
            self._storage_callback(entry)

        return entry

    def log_call_event(
        self,
        call_id: str,
        action: AuditAction,
        patient_id: UUID | None = None,
        details: dict[str, Any] | None = None,
    ) -> AuditLogEntry:
        """Log a call-related event."""
        return self.log(
            action=action,
            actor_id="phone_agent",
            actor_type="ai_agent",
            resource_type="call",
            resource_id=call_id,
            patient_id=patient_id,
            details=details,
        )

    def log_data_access(
        self,
        actor_id: str,
        resource_type: str,
        resource_id: str,
        patient_id: UUID | None = None,
        access_type: str = "view",
    ) -> AuditLogEntry:
        """Log a data access event."""
        action_map = {
            "view": AuditAction.DATA_VIEW,
            "export": AuditAction.DATA_EXPORT,
            "search": AuditAction.DATA_SEARCH,
        }

        return self.log(
            action=action_map.get(access_type, AuditAction.DATA_VIEW),
            actor_id=actor_id,
            actor_type="ai_agent",
            resource_type=resource_type,
            resource_id=resource_id,
            patient_id=patient_id,
            details={"access_type": access_type},
        )

    def get_patient_access_log(
        self,
        patient_id: UUID,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[AuditLogEntry]:
        """Get audit log entries for a specific patient."""
        entries = [
            e for e in self._logs
            if e.patient_id == patient_id
        ]

        if start_date:
            entries = [e for e in entries if e.timestamp >= start_date]

        if end_date:
            entries = [e for e in entries if e.timestamp <= end_date]

        return sorted(entries, key=lambda e: e.timestamp, reverse=True)

    def export_audit_log(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        format: str = "json",
    ) -> str:
        """Export audit log for compliance reporting."""
        entries = self._logs

        if start_date:
            entries = [e for e in entries if e.timestamp >= start_date]

        if end_date:
            entries = [e for e in entries if e.timestamp <= end_date]

        if format == "json":
            return json.dumps(
                [e.to_dict() for e in entries],
                indent=2,
                ensure_ascii=False,
            )

        # CSV format
        lines = ["timestamp,action,actor_id,resource_type,resource_id,patient_id,checksum"]
        for e in entries:
            lines.append(
                f"{e.timestamp.isoformat()},{e.action.value},{e.actor_id},"
                f"{e.resource_type},{e.resource_id or ''},"
                f"{e.patient_id or ''},{e.checksum or ''}"
            )

        return "\n".join(lines)


class DataProtectionService:
    """DSGVO/GDPR data protection service."""

    def __init__(self):
        """Initialize data protection service."""
        self._retention_policies = {
            p.resource_type: p for p in DEFAULT_RETENTION_POLICIES
        }

    def anonymize_patient_data(
        self,
        data: dict[str, Any],
        fields_to_anonymize: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Anonymize patient data.

        Args:
            data: Patient data dictionary
            fields_to_anonymize: Specific fields to anonymize

        Returns:
            Anonymized data
        """
        default_fields = [
            "first_name", "last_name", "name", "phone", "email",
            "address", "insurance_number", "date_of_birth",
        ]

        fields = fields_to_anonymize or default_fields
        result = data.copy()

        for field in fields:
            if field in result:
                if field in ["first_name", "last_name", "name"]:
                    result[field] = "***"
                elif field in ["phone"]:
                    result[field] = "***" + str(result[field])[-4:] if result[field] else None
                elif field in ["email"]:
                    if result[field] and "@" in result[field]:
                        parts = result[field].split("@")
                        result[field] = "***@" + parts[1]
                elif field in ["date_of_birth"]:
                    if result[field]:
                        # Keep only year
                        if isinstance(result[field], date):
                            result[field] = result[field].replace(month=1, day=1)
                        else:
                            result[field] = "****-**-**"
                else:
                    result[field] = "***"

        return result

    def pseudonymize_patient_id(self, patient_id: UUID) -> str:
        """
        Create pseudonym for patient ID.

        Args:
            patient_id: Original patient ID

        Returns:
            Pseudonymized ID
        """
        # Create hash-based pseudonym
        hash_input = f"{patient_id}:itf_salt_2024"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:16]

    def get_retention_policy(self, resource_type: str) -> DataRetentionPolicy | None:
        """Get retention policy for a resource type."""
        return self._retention_policies.get(resource_type)

    def check_retention_expired(
        self,
        resource_type: str,
        created_at: datetime,
    ) -> bool:
        """Check if data retention period has expired."""
        policy = self._retention_policies.get(resource_type)
        if not policy:
            return False

        expiry_date = created_at + timedelta(days=policy.retention_days)
        return datetime.now() > expiry_date

    def get_data_subject_rights_info(self, language: str = "de") -> dict[str, str]:
        """Get information about data subject rights (DSGVO Art. 15-22)."""
        if language == "de":
            return {
                "right_of_access": "Sie haben das Recht, Auskunft über Ihre gespeicherten personenbezogenen Daten zu verlangen (Art. 15 DSGVO).",
                "right_to_rectification": "Sie haben das Recht, die Berichtigung unrichtiger Daten zu verlangen (Art. 16 DSGVO).",
                "right_to_erasure": "Sie haben das Recht auf Löschung Ihrer Daten, sofern keine gesetzlichen Aufbewahrungspflichten bestehen (Art. 17 DSGVO).",
                "right_to_restriction": "Sie haben das Recht auf Einschränkung der Verarbeitung (Art. 18 DSGVO).",
                "right_to_data_portability": "Sie haben das Recht, Ihre Daten in einem gängigen Format zu erhalten (Art. 20 DSGVO).",
                "right_to_object": "Sie haben das Recht, der Verarbeitung zu widersprechen (Art. 21 DSGVO).",
                "right_to_withdraw_consent": "Sie können Ihre Einwilligung jederzeit widerrufen.",
                "contact": "Wenden Sie sich für Anfragen an unsere Praxis oder den Datenschutzbeauftragten.",
            }

        return {
            "right_of_access": "You have the right to access your stored personal data (Art. 15 GDPR).",
            "right_to_rectification": "You have the right to request correction of inaccurate data (Art. 16 GDPR).",
            "right_to_erasure": "You have the right to erasure of your data (Art. 17 GDPR).",
            "right_to_restriction": "You have the right to restriction of processing (Art. 18 GDPR).",
            "right_to_data_portability": "You have the right to receive your data in a portable format (Art. 20 GDPR).",
            "right_to_object": "You have the right to object to processing (Art. 21 GDPR).",
            "right_to_withdraw_consent": "You may withdraw your consent at any time.",
            "contact": "Contact our practice or data protection officer for inquiries.",
        }


# Singleton instances
_consent_manager: ConsentManager | None = None
_audit_logger: AuditLogger | None = None
_data_protection_service: DataProtectionService | None = None


def get_consent_manager() -> ConsentManager:
    """Get or create consent manager singleton."""
    global _consent_manager
    if _consent_manager is None:
        _consent_manager = ConsentManager()
    return _consent_manager


def get_audit_logger() -> AuditLogger:
    """Get or create audit logger singleton."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger


def get_data_protection_service() -> DataProtectionService:
    """Get or create data protection service singleton."""
    global _data_protection_service
    if _data_protection_service is None:
        _data_protection_service = DataProtectionService()
    return _data_protection_service
