# ADR 0002: Industry Module Pattern

## Status

Accepted

## Date

2024-12-01

## Context

IT-Friends Phone Agent targets multiple German SME industries:
- Gesundheit (Healthcare)
- Handwerk (Trades)
- Gastro (Hospitality)
- Freie Berufe (Professionals)
- And more...

Each industry has:
- Different conversation flows (triage vs. job intake vs. reservations)
- Different terminology (Symptome vs. Schadensart vs. Personenzahl)
- Different compliance requirements (medical data vs. standard business)
- Different scheduling patterns (appointment types, durations, buffers)

We needed a pattern that allows:
1. Maximum code reuse across industries
2. Clear separation of industry-specific logic
3. Easy addition of new industries
4. Independent testing per industry

## Decision

We adopted a **modular industry package pattern** where each industry is a self-contained Python package under `src/phone_agent/industry/<name>/`.

### Standard Module Structure

```
industry/<name>/
├── __init__.py          # Public exports, factory functions
├── prompts.py           # German-language conversation prompts
├── workflows.py         # Basic workflow definitions, enums
├── triage.py            # Domain-specific triage/intake engine
├── scheduling.py        # Appointment/booking management
├── compliance.py        # Industry-specific compliance rules
├── conversation.py      # Conversation state machine (optional)
└── <domain_specific>/   # Additional domain modules
    ├── recall.py        # (Gesundheit: patient recall)
    ├── technician.py    # (Handwerk: technician dispatch)
    └── ...
```

### Required Components

Every industry module MUST implement:

1. **`prompts.py`**: German-language prompts
   - `SYSTEM_PROMPT`: LLM system context
   - `GREETING_PROMPT`: Call greeting template
   - `FAREWELL_PROMPT`: Call ending template
   - Domain-specific prompts (TRIAGE_PROMPT, INTAKE_PROMPT, etc.)

2. **`workflows.py`**: Core domain enums
   - `UrgencyLevel` or equivalent prioritization
   - `ServiceType` or equivalent categorization
   - Basic workflow function for simple cases

3. **`triage.py`** or **`intake.py`**: Primary decision engine
   - Takes caller input and context
   - Returns structured result with action recommendation
   - Implements domain-specific logic (symptoms, job types, etc.)

4. **`scheduling.py`**: Time slot management
   - Available slot queries
   - Booking creation
   - Duration and buffer rules per appointment type

5. **`compliance.py`**: Regulatory compliance
   - Consent types required
   - Data retention policies
   - Audit logging requirements

### Factory Pattern

Each module exposes factory functions for dependency injection:

```python
# industry/gesundheit/__init__.py
def get_triage_engine() -> TriageEngine:
    """Get or create singleton triage engine."""

def get_scheduling_service() -> SchedulingService:
    """Get or create scheduling service."""

def get_consent_manager() -> ConsentManager:
    """Get or create consent manager."""
```

### Configuration Integration

Industries are selected via configuration:

```yaml
# configs/production.yaml
industry:
  name: "gesundheit"
  features:
    triage_enabled: true
    recall_campaigns: true
```

## Consequences

### Positive

1. **Clear Boundaries**: Each industry is fully encapsulated
2. **Independent Testing**: `tests/test_healthcare.py`, `tests/test_handwerk.py`, etc.
3. **Code Reuse**: Shared base classes (BaseTriageEngine, BaseSchedulingService)
4. **Easy Extension**: Copy existing module, modify for new industry
5. **Type Safety**: Each module defines its own Pydantic models

### Negative

1. **Potential Duplication**: Some similar code across industries
2. **Learning Curve**: Contributors must understand the pattern
3. **Migration Effort**: Adding shared features requires updating all modules

### Trade-offs Accepted

- We accept some duplication to maintain clear separation
- Industry-specific needs outweigh DRY concerns
- Pattern documentation (INDUSTRY_MODULE_GUIDE.md) mitigates learning curve

## Implementation Examples

### Gesundheit (Healthcare)

```python
# Primary: Symptom-based triage
class TriageEngine:
    def assess(self, symptoms: list[Symptom], context: PatientContext) -> TriageResult

# Urgency levels follow KBV Bereitschaftsdienst guidelines
class UrgencyLevel(Enum):
    AKUT = "akut"           # Emergency transfer
    DRINGEND = "dringend"   # Same-day appointment
    NORMAL = "normal"       # Regular scheduling
    BERATUNG = "beratung"   # Phone consultation only
```

### Handwerk (Trades)

```python
# Primary: Job type classification
class JobIntakeEngine:
    def classify(self, description: str, urgency: str) -> JobClassification

# Service types for trade businesses
class ServiceType(Enum):
    NOTDIENST = "notdienst"       # Emergency repair
    REPARATUR = "reparatur"       # Standard repair
    WARTUNG = "wartung"           # Maintenance
    BERATUNG = "beratung"         # Consultation
```

## Related Decisions

- [ADR 0003: German Language Optimization](./0003-german-language-optimization.md)
- [ADR 0005: DSGVO Compliance Architecture](./0005-dsgvo-compliance-architecture.md)
