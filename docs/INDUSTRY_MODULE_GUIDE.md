# Industry Module Developer Guide

This guide explains how to add new industry modules to IT-Friends Phone Agent.

## Overview

Each industry (Gesundheit, Handwerk, Gastro, etc.) is implemented as a self-contained Python package under `src/phone_agent/industry/<name>/`. This modular design enables:

- Maximum code reuse across industries
- Clear separation of industry-specific logic
- Independent testing per industry
- Easy addition of new industries

## Quick Start

To add a new industry module:

```bash
# 1. Create the directory structure
mkdir -p src/phone_agent/industry/new_industry

# 2. Copy from an existing industry
cp -r src/phone_agent/industry/gesundheit/* src/phone_agent/industry/new_industry/

# 3. Modify the files for your industry
# 4. Add tests
# 5. Register in configuration
```

## Module Structure

Every industry module MUST follow this structure:

```
industry/<name>/
├── __init__.py          # Public exports, factory functions
├── prompts.py           # German-language conversation prompts
├── workflows.py         # Basic workflow definitions, enums
├── triage.py            # Domain-specific triage/intake engine
├── scheduling.py        # Appointment/booking management
├── compliance.py        # Industry-specific compliance rules
├── conversation.py      # Conversation state machine (optional)
└── <domain_specific>/   # Additional domain modules (optional)
```

## Required Components

### 1. `__init__.py` - Module Exports

This file defines the public API of your industry module.

```python
"""New Industry module for Phone Agent.

Implements automation for <industry description>:
- Key feature 1
- Key feature 2
- DSGVO/GDPR compliance
"""

# Import and export all public components
from phone_agent.industry.new_industry.prompts import (
    SYSTEM_PROMPT,
    GREETING_PROMPT,
    INTAKE_PROMPT,
    FAREWELL_PROMPT,
)

from phone_agent.industry.new_industry.workflows import (
    ServiceType,
    UrgencyLevel,
)

from phone_agent.industry.new_industry.triage import (
    IntakeEngine,
    IntakeResult,
    get_intake_engine,
)

from phone_agent.industry.new_industry.scheduling import (
    SchedulingService,
    TimeSlot,
    Booking,
    get_scheduling_service,
)

from phone_agent.industry.new_industry.compliance import (
    ConsentManager,
    ConsentType,
    get_consent_manager,
)

__all__ = [
    # Prompts
    "SYSTEM_PROMPT",
    "GREETING_PROMPT",
    "INTAKE_PROMPT",
    "FAREWELL_PROMPT",
    # Workflows
    "ServiceType",
    "UrgencyLevel",
    # Intake
    "IntakeEngine",
    "IntakeResult",
    "get_intake_engine",
    # Scheduling
    "SchedulingService",
    "TimeSlot",
    "Booking",
    "get_scheduling_service",
    # Compliance
    "ConsentManager",
    "ConsentType",
    "get_consent_manager",
]
```

### 2. `prompts.py` - German Conversation Prompts

All prompts MUST be in German using formal "Sie" form.

```python
"""German-language prompts for <industry>."""

SYSTEM_PROMPT = """
Du bist ein freundlicher und professioneller Telefonassistent für
{business_name}. Deine Aufgaben sind:
- Anrufe entgegennehmen und weiterleiten
- Termine vereinbaren
- Informationen bereitstellen

Wichtige Regeln:
- Sprich immer höflich mit "Sie"
- Verwende klare, einfache Sprache
- Frage bei Unklarheiten nach
- Zeiten im 24-Stunden-Format (z.B. 14:30 Uhr)
- Daten im deutschen Format (z.B. 15.01.2025)
"""

GREETING_PROMPT = """
Guten {time_of_day}, hier ist {business_name}.
Wie kann ich Ihnen helfen?
"""

INTAKE_PROMPT = """
Ich verstehe, Sie möchten {service_type}.
Können Sie mir bitte mehr dazu erzählen?
"""

CONFIRMATION_PROMPT = """
Ich fasse zusammen: {summary}

Ist das so richtig?
"""

FAREWELL_PROMPT = """
Vielen Dank für Ihren Anruf bei {business_name}.
Auf Wiederhören!
"""
```

### 3. `workflows.py` - Core Enums and Simple Workflows

Define the domain-specific enums and basic workflow functions.

```python
"""Workflow definitions for <industry>."""

from enum import Enum
from dataclasses import dataclass


class ServiceType(str, Enum):
    """Types of services offered."""

    TYPE_A = "type_a"
    TYPE_B = "type_b"
    CONSULTATION = "consultation"
    OTHER = "other"


class UrgencyLevel(str, Enum):
    """Urgency levels for requests."""

    IMMEDIATE = "immediate"    # Needs immediate attention
    SAME_DAY = "same_day"      # Should be handled today
    NORMAL = "normal"          # Standard scheduling
    LOW = "low"                # Can wait, no urgency


@dataclass
class WorkflowResult:
    """Result of a basic workflow assessment."""

    service_type: ServiceType
    urgency: UrgencyLevel
    notes: str = ""


def assess_request(description: str) -> WorkflowResult:
    """Basic request assessment (for simple cases)."""
    # Simple keyword matching for basic cases
    description_lower = description.lower()

    if "dringend" in description_lower or "sofort" in description_lower:
        urgency = UrgencyLevel.IMMEDIATE
    elif "heute" in description_lower:
        urgency = UrgencyLevel.SAME_DAY
    else:
        urgency = UrgencyLevel.NORMAL

    return WorkflowResult(
        service_type=ServiceType.OTHER,
        urgency=urgency,
        notes=description,
    )
```

### 4. `triage.py` - Domain-Specific Intake Engine

The main decision engine for classifying and routing requests.

```python
"""Intake engine for <industry>."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from phone_agent.industry.new_industry.workflows import (
    ServiceType,
    UrgencyLevel,
)


@dataclass
class IntakeContext:
    """Context about the caller/request."""

    caller_name: Optional[str] = None
    caller_phone: str = ""
    previous_customer: bool = False
    special_requirements: list[str] = field(default_factory=list)


@dataclass
class IntakeResult:
    """Result of intake assessment."""

    service_type: ServiceType
    urgency: UrgencyLevel
    recommended_action: str
    reasoning: str
    confidence: float = 0.8
    suggested_response: str = ""
    metadata: dict = field(default_factory=dict)


class IntakeEngine:
    """Main intake/triage engine for <industry>."""

    def __init__(self):
        self._rules = self._load_rules()

    def _load_rules(self) -> dict:
        """Load industry-specific classification rules."""
        return {
            # Keywords and their classifications
            "keyword_mappings": {
                "dringend": UrgencyLevel.IMMEDIATE,
                "notfall": UrgencyLevel.IMMEDIATE,
                "heute": UrgencyLevel.SAME_DAY,
            },
            "service_keywords": {
                "beratung": ServiceType.CONSULTATION,
                # Add industry-specific mappings
            }
        }

    def assess(
        self,
        description: str,
        context: Optional[IntakeContext] = None,
    ) -> IntakeResult:
        """Assess a customer request and determine routing."""
        context = context or IntakeContext()

        # Analyze the request
        service_type = self._classify_service(description)
        urgency = self._assess_urgency(description, context)
        action = self._determine_action(service_type, urgency)

        return IntakeResult(
            service_type=service_type,
            urgency=urgency,
            recommended_action=action,
            reasoning=f"Klassifiziert als {service_type.value}",
            suggested_response=self._generate_response(service_type, urgency),
        )

    def _classify_service(self, description: str) -> ServiceType:
        """Classify the type of service requested."""
        description_lower = description.lower()

        for keyword, service_type in self._rules["service_keywords"].items():
            if keyword in description_lower:
                return service_type

        return ServiceType.OTHER

    def _assess_urgency(
        self,
        description: str,
        context: IntakeContext,
    ) -> UrgencyLevel:
        """Assess the urgency of the request."""
        description_lower = description.lower()

        for keyword, urgency in self._rules["keyword_mappings"].items():
            if keyword in description_lower:
                return urgency

        return UrgencyLevel.NORMAL

    def _determine_action(
        self,
        service_type: ServiceType,
        urgency: UrgencyLevel,
    ) -> str:
        """Determine the recommended action."""
        if urgency == UrgencyLevel.IMMEDIATE:
            return "transfer_to_staff"
        elif urgency == UrgencyLevel.SAME_DAY:
            return "schedule_same_day"
        else:
            return "schedule_normal"

    def _generate_response(
        self,
        service_type: ServiceType,
        urgency: UrgencyLevel,
    ) -> str:
        """Generate a suggested response for the caller."""
        if urgency == UrgencyLevel.IMMEDIATE:
            return "Ich verbinde Sie sofort mit einem Mitarbeiter."
        elif urgency == UrgencyLevel.SAME_DAY:
            return "Ich suche einen Termin für heute."
        else:
            return "Gerne vereinbare ich einen Termin für Sie."


# Singleton factory
_intake_engine: Optional[IntakeEngine] = None


def get_intake_engine() -> IntakeEngine:
    """Get or create singleton intake engine."""
    global _intake_engine
    if _intake_engine is None:
        _intake_engine = IntakeEngine()
    return _intake_engine
```

### 5. `scheduling.py` - Appointment/Booking Management

```python
"""Scheduling service for <industry>."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time, datetime, timedelta
from typing import Optional
from enum import Enum


class BookingType(str, Enum):
    """Types of bookings."""

    STANDARD = "standard"
    EXTENDED = "extended"
    CONSULTATION = "consultation"


@dataclass
class TimeSlot:
    """Available time slot."""

    start: time
    end: time
    available: bool = True
    booking_type: Optional[BookingType] = None


@dataclass
class Booking:
    """A confirmed booking."""

    id: str
    customer_name: str
    customer_phone: str
    date: date
    start_time: time
    end_time: time
    booking_type: BookingType
    notes: str = ""
    confirmed: bool = False


@dataclass
class BookingPreferences:
    """Customer preferences for booking."""

    preferred_date: Optional[date] = None
    preferred_time_range: tuple[time, time] = (time(9, 0), time(17, 0))
    booking_type: BookingType = BookingType.STANDARD
    special_requirements: list[str] = None


class SchedulingService:
    """Manages bookings and time slots."""

    def __init__(self):
        self.default_slot_duration = 30  # minutes
        self.business_hours = {
            0: (time(8, 0), time(18, 0)),   # Monday
            1: (time(8, 0), time(18, 0)),   # Tuesday
            2: (time(8, 0), time(13, 0)),   # Wednesday
            3: (time(8, 0), time(18, 0)),   # Thursday
            4: (time(8, 0), time(14, 0)),   # Friday
            5: None,  # Saturday - closed
            6: None,  # Sunday - closed
        }

    async def get_available_slots(
        self,
        target_date: date,
        duration: int = None,
    ) -> list[TimeSlot]:
        """Get available time slots for a date."""
        duration = duration or self.default_slot_duration
        weekday = target_date.weekday()

        hours = self.business_hours.get(weekday)
        if not hours:
            return []  # Closed

        start_time, end_time = hours
        slots = []

        current = datetime.combine(target_date, start_time)
        end = datetime.combine(target_date, end_time)

        while current + timedelta(minutes=duration) <= end:
            slot_end = (current + timedelta(minutes=duration)).time()
            slots.append(TimeSlot(
                start=current.time(),
                end=slot_end,
                available=True,  # TODO: Check against existing bookings
            ))
            current += timedelta(minutes=duration)

        return slots

    async def find_next_available(
        self,
        preferences: BookingPreferences,
        search_days: int = 14,
    ) -> Optional[TimeSlot]:
        """Find the next available slot matching preferences."""
        start_date = preferences.preferred_date or date.today()

        for i in range(search_days):
            check_date = start_date + timedelta(days=i)
            slots = await self.get_available_slots(check_date)

            for slot in slots:
                if slot.available:
                    pref_start, pref_end = preferences.preferred_time_range
                    if pref_start <= slot.start <= pref_end:
                        return slot

        return None

    async def create_booking(
        self,
        customer_name: str,
        customer_phone: str,
        booking_date: date,
        slot: TimeSlot,
        booking_type: BookingType = BookingType.STANDARD,
        notes: str = "",
    ) -> Booking:
        """Create a new booking."""
        import uuid

        booking = Booking(
            id=str(uuid.uuid4()),
            customer_name=customer_name,
            customer_phone=customer_phone,
            date=booking_date,
            start_time=slot.start,
            end_time=slot.end,
            booking_type=booking_type,
            notes=notes,
            confirmed=False,
        )

        # TODO: Persist to database

        return booking


# Singleton factory
_scheduling_service: Optional[SchedulingService] = None


def get_scheduling_service() -> SchedulingService:
    """Get or create singleton scheduling service."""
    global _scheduling_service
    if _scheduling_service is None:
        _scheduling_service = SchedulingService()
    return _scheduling_service
```

### 6. `compliance.py` - Industry-Specific Compliance

```python
"""Compliance management for <industry>."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class ConsentType(str, Enum):
    """Types of consent required."""

    CALL_RECORDING = "call_recording"
    DATA_PROCESSING = "data_processing"
    REMINDERS = "reminders"
    MARKETING = "marketing"


@dataclass
class Consent:
    """A consent record."""

    customer_id: str
    consent_type: ConsentType
    granted: bool
    granted_at: datetime
    method: str  # "verbal", "written", "digital"
    expires_at: Optional[datetime] = None
    call_id: Optional[str] = None


class ConsentManager:
    """Manages customer consent."""

    # Industry-specific required consents
    REQUIRED_CONSENTS = [
        ConsentType.DATA_PROCESSING,
    ]

    OPTIONAL_CONSENTS = [
        ConsentType.CALL_RECORDING,
        ConsentType.REMINDERS,
    ]

    async def request_consent(
        self,
        customer_id: str,
        consent_type: ConsentType,
        method: str = "verbal",
        call_id: Optional[str] = None,
    ) -> Consent:
        """Record consent granted by customer."""
        consent = Consent(
            customer_id=customer_id,
            consent_type=consent_type,
            granted=True,
            granted_at=datetime.now(),
            method=method,
            call_id=call_id,
        )

        # TODO: Persist to database
        # TODO: Log to audit trail

        return consent

    async def verify_consent(
        self,
        customer_id: str,
        consent_type: ConsentType,
    ) -> bool:
        """Check if customer has granted consent."""
        # TODO: Check database
        return False

    async def revoke_consent(
        self,
        customer_id: str,
        consent_type: ConsentType,
    ) -> None:
        """Revoke previously granted consent."""
        # TODO: Update database
        # TODO: Log to audit trail
        pass

    def get_required_consents(self) -> list[ConsentType]:
        """Get list of required consents for this industry."""
        return self.REQUIRED_CONSENTS


# Singleton factory
_consent_manager: Optional[ConsentManager] = None


def get_consent_manager() -> ConsentManager:
    """Get or create singleton consent manager."""
    global _consent_manager
    if _consent_manager is None:
        _consent_manager = ConsentManager()
    return _consent_manager
```

## Testing Your Industry Module

Create tests in `tests/test_<industry>.py`:

```python
"""Tests for <industry> module."""

import pytest
from datetime import date, time

from phone_agent.industry.new_industry import (
    SYSTEM_PROMPT,
    GREETING_PROMPT,
    ServiceType,
    UrgencyLevel,
    get_intake_engine,
    get_scheduling_service,
    get_consent_manager,
)


class TestPrompts:
    """Test German prompts."""

    def test_system_prompt_is_german(self):
        assert "Sie" in SYSTEM_PROMPT
        assert "freundlich" in SYSTEM_PROMPT.lower()

    def test_greeting_has_placeholders(self):
        assert "{business_name}" in GREETING_PROMPT


class TestIntakeEngine:
    """Test intake classification."""

    def test_urgent_request(self):
        engine = get_intake_engine()
        result = engine.assess("Das ist dringend, ich brauche sofort Hilfe")

        assert result.urgency == UrgencyLevel.IMMEDIATE
        assert result.recommended_action == "transfer_to_staff"

    def test_normal_request(self):
        engine = get_intake_engine()
        result = engine.assess("Ich möchte gerne einen Termin vereinbaren")

        assert result.urgency == UrgencyLevel.NORMAL
        assert result.recommended_action == "schedule_normal"


class TestScheduling:
    """Test scheduling service."""

    @pytest.mark.asyncio
    async def test_get_slots_for_weekday(self):
        service = get_scheduling_service()
        # Use a known Monday
        monday = date(2025, 1, 6)

        slots = await service.get_available_slots(monday)

        assert len(slots) > 0
        assert all(slot.available for slot in slots)

    @pytest.mark.asyncio
    async def test_no_slots_on_sunday(self):
        service = get_scheduling_service()
        # Use a known Sunday
        sunday = date(2025, 1, 5)

        slots = await service.get_available_slots(sunday)

        assert len(slots) == 0


class TestCompliance:
    """Test compliance management."""

    def test_required_consents(self):
        manager = get_consent_manager()
        required = manager.get_required_consents()

        assert len(required) > 0
```

Run tests:
```bash
pytest tests/test_new_industry.py -v
```

## Configuration Integration

### Register the Industry

Add to `configs/default.yaml`:

```yaml
industry:
  name: "new_industry"
  display_name: "New Industry Display Name"

  features:
    intake_enabled: true
    scheduling_enabled: true
    reminders_enabled: true

  hours:
    monday: "08:00-18:00"
    tuesday: "08:00-18:00"
    wednesday: "08:00-13:00"
    thursday: "08:00-18:00"
    friday: "08:00-14:00"
    saturday: null
    sunday: null
```

### Dynamic Industry Loading

The industry module is loaded based on configuration:

```python
# In application startup
from phone_agent.config import get_settings

settings = get_settings()
industry_name = settings.industry.name

# Dynamic import
industry_module = importlib.import_module(
    f"phone_agent.industry.{industry_name}"
)
```

## Best Practices

### DO

- Use German "Sie" form in all prompts
- Follow existing module structure exactly
- Write comprehensive tests (aim for >80% coverage)
- Use Pydantic models for data validation
- Use factory functions for singletons
- Log all significant actions for audit trail
- Handle consent explicitly

### DON'T

- Mix languages in prompts (German only)
- Use informal "Du" form
- Skip compliance components
- Hardcode business-specific values
- Forget timezone handling (always Europe/Berlin)

## Industry Module Checklist

Before submitting a new industry module:

- [ ] `__init__.py` exports all public components
- [ ] All prompts are in German with "Sie" form
- [ ] `workflows.py` defines ServiceType and UrgencyLevel
- [ ] `triage.py` or equivalent intake engine works
- [ ] `scheduling.py` handles business hours correctly
- [ ] `compliance.py` defines required consents
- [ ] At least 20 tests pass
- [ ] Module loads without errors
- [ ] Configuration entry added

## Reference Implementations

Study these existing implementations:

1. **Gesundheit (Healthcare)** - Most complete, with triage, recall, and full compliance
2. **Handwerk (Trades)** - Job intake, technician dispatch

Location: `src/phone_agent/industry/`

---

*Questions? Check the ADRs in `docs/adr/` or open an issue.*
