"""Triage API endpoints."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from phone_agent.industry.gesundheit import (
    get_triage_engine,
    Symptom,
    SymptomCategory,
    PatientContext,
    UrgencyLevel,
)


router = APIRouter(prefix="/triage")


class SymptomInput(BaseModel):
    """Input model for a symptom."""

    name: str = Field(..., description="Symptom name")
    category: str = Field(default="general", description="Symptom category")
    severity: int = Field(ge=1, le=10, default=5, description="Severity (1-10)")
    duration_hours: float | None = Field(default=None, description="Duration in hours")
    is_worsening: bool = Field(default=False, description="Is symptom worsening")
    fever: bool = Field(default=False, description="Has fever")
    fever_temp: float | None = Field(default=None, description="Fever temperature")
    pain_level: int | None = Field(ge=1, le=10, default=None, description="Pain level (1-10)")


class PatientInput(BaseModel):
    """Input model for patient context."""

    age: int | None = Field(default=None, description="Patient age")
    gender: str | None = Field(default=None, description="Gender (M/F)")
    is_pregnant: bool = Field(default=False, description="Is pregnant")
    is_diabetic: bool = Field(default=False, description="Is diabetic")
    is_immunocompromised: bool = Field(default=False, description="Is immunocompromised")
    has_heart_condition: bool = Field(default=False, description="Has heart condition")
    chronic_conditions: list[str] = Field(default_factory=list, description="Chronic conditions")


class TriageRequest(BaseModel):
    """Request model for triage assessment."""

    free_text: str | None = Field(default=None, description="Patient's description in German")
    symptoms: list[SymptomInput] = Field(default_factory=list, description="List of symptoms")
    patient: PatientInput | None = Field(default=None, description="Patient context")


class TriageResponse(BaseModel):
    """Response model for triage assessment."""

    urgency: str
    urgency_display: str
    risk_score: float
    primary_concern: str
    recommended_action: str
    max_wait_minutes: int | None
    requires_callback: bool
    requires_doctor: bool
    emergency_symptoms: list[str]
    assessment_notes: list[str]
    extracted_symptoms: list[dict[str, Any]]


# Urgency level display names (German)
URGENCY_DISPLAY = {
    UrgencyLevel.EMERGENCY: "Notfall - Sofort 112 rufen",
    UrgencyLevel.VERY_URGENT: "Sehr dringend - Sofort in die Praxis",
    UrgencyLevel.URGENT: "Dringend - Heute noch",
    UrgencyLevel.STANDARD: "Normal - Zeitnah",
    UrgencyLevel.NON_URGENT: "Nicht dringend - Regeltermin",
}


@router.post("", response_model=TriageResponse)
async def assess_triage(request: TriageRequest) -> TriageResponse:
    """
    Perform triage assessment.

    Analyzes symptoms and patient context to determine urgency level
    and recommended action. Supports both structured symptoms and
    free-text description in German.
    """
    engine = get_triage_engine()

    # Convert input symptoms
    symptoms: list[Symptom] = []
    for s in request.symptoms:
        try:
            category = SymptomCategory(s.category)
        except ValueError:
            category = SymptomCategory.GENERAL

        symptoms.append(Symptom(
            name=s.name,
            category=category,
            severity=s.severity,
            duration_hours=s.duration_hours,
            is_worsening=s.is_worsening,
            fever=s.fever,
            fever_temp=s.fever_temp,
            pain_level=s.pain_level,
        ))

    # Convert patient context
    patient = None
    if request.patient:
        patient = PatientContext(
            age=request.patient.age,
            gender=request.patient.gender,
            is_pregnant=request.patient.is_pregnant,
            is_diabetic=request.patient.is_diabetic,
            is_immunocompromised=request.patient.is_immunocompromised,
            has_heart_condition=request.patient.has_heart_condition,
            chronic_conditions=request.patient.chronic_conditions,
        )

    # Extract symptoms from free text if provided
    extracted = []
    if request.free_text:
        extracted = engine.extract_symptoms_from_text(request.free_text)
        symptoms.extend(extracted)

    # Perform triage
    result = engine.assess(
        symptoms=symptoms,
        patient=patient,
        free_text=request.free_text,
    )

    return TriageResponse(
        urgency=result.urgency.value,
        urgency_display=URGENCY_DISPLAY.get(result.urgency, result.urgency.value),
        risk_score=result.risk_score,
        primary_concern=result.primary_concern,
        recommended_action=result.recommended_action,
        max_wait_minutes=result.max_wait_minutes,
        requires_callback=result.requires_callback,
        requires_doctor=result.requires_doctor,
        emergency_symptoms=result.emergency_symptoms,
        assessment_notes=result.assessment_notes,
        extracted_symptoms=[s.to_dict() for s in extracted],
    )


@router.post("/extract-symptoms")
async def extract_symptoms(text: str) -> list[dict[str, Any]]:
    """
    Extract symptoms from free-text description.

    Analyzes German text to identify mentioned symptoms.
    """
    engine = get_triage_engine()
    symptoms = engine.extract_symptoms_from_text(text)
    return [s.to_dict() for s in symptoms]


@router.get("/categories")
async def get_symptom_categories() -> list[dict[str, str]]:
    """Get available symptom categories."""
    return [
        {"value": cat.value, "name": cat.name}
        for cat in SymptomCategory
    ]


@router.get("/urgency-levels")
async def get_urgency_levels() -> list[dict[str, Any]]:
    """Get urgency levels with descriptions."""
    return [
        {
            "value": level.value,
            "name": level.name,
            "display": URGENCY_DISPLAY.get(level, level.value),
        }
        for level in UrgencyLevel
    ]
