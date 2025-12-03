"""Technician models and matching for Handwerk.

Implements:
- Technician data models with skills and certifications
- Availability tracking
- Intelligent job-to-technician matching
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date, time, timedelta
from enum import Enum
from typing import Any
from uuid import UUID, uuid4


class TechnicianQualification(str, Enum):
    """German trade qualifications."""

    MEISTER = "meister"           # Master craftsman
    GESELLE = "geselle"           # Journeyman
    FACHARBEITER = "facharbeiter" # Skilled worker
    LEHRLING = "lehrling"         # Apprentice
    HELFER = "helfer"             # Helper/Assistant


class TradeSpecialty(str, Enum):
    """Trade specialties (Gewerke)."""

    SHK = "shk"                    # Sanitär, Heizung, Klima
    ELEKTRO = "elektro"           # Electrical
    SCHLOSSER = "schlosser"       # Locksmith
    DACHDECKER = "dachdecker"     # Roofing
    MALER = "maler"               # Painting
    TISCHLER = "tischler"         # Carpentry
    BAU = "bau"                   # Construction
    KLIMA = "klima"               # Climate/HVAC


class CertificationType(str, Enum):
    """Professional certifications."""

    GAS_BERECHTIGUNG = "gas"            # Gas installation permit
    ELEKTRO_BERECHTIGUNG = "elektro"    # Electrical installation permit
    SCHEIN_B = "schein_b"               # Excavation permit
    ASBESTSANIERUNG = "asbest"          # Asbestos removal
    KAELTEMITTEL = "kaelte"             # Refrigerant handling
    SCHWEISSEN = "schweiss"             # Welding certification


@dataclass
class Technician:
    """Technician profile with skills and availability."""

    id: UUID
    name: str
    phone: str
    email: str | None = None

    # Skills and qualifications
    qualification: TechnicianQualification = TechnicianQualification.GESELLE
    specialties: list[TradeSpecialty] = field(default_factory=list)
    certifications: list[CertificationType] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)  # Specific skills
    years_experience: int = 0

    # Availability
    max_travel_radius_km: int = 30
    home_base_lat: float | None = None
    home_base_lon: float | None = None
    current_lat: float | None = None
    current_lon: float | None = None
    available_from: datetime | None = None
    available_until: datetime | None = None

    # Workload
    workload_minutes_today: int = 0
    max_workload_minutes: int = 480  # 8 hours
    current_job_id: UUID | None = None
    jobs_today: int = 0
    max_jobs_per_day: int = 6

    # Vehicle
    vehicle_type: str = "van"  # "van", "car", "bike"
    has_tools: bool = True
    has_ladder: bool = False
    has_drain_camera: bool = False

    # Status
    is_active: bool = True
    is_on_emergency_duty: bool = False

    @property
    def remaining_capacity_minutes(self) -> int:
        """Get remaining work capacity for today."""
        return max(0, self.max_workload_minutes - self.workload_minutes_today)

    @property
    def remaining_jobs(self) -> int:
        """Get remaining job slots for today."""
        return max(0, self.max_jobs_per_day - self.jobs_today)

    @property
    def is_available(self) -> bool:
        """Check if technician is currently available."""
        if not self.is_active:
            return False
        if self.current_job_id is not None:
            return False
        if self.remaining_capacity_minutes <= 0:
            return False
        if self.remaining_jobs <= 0:
            return False

        now = datetime.now()
        if self.available_from and now < self.available_from:
            return False
        if self.available_until and now > self.available_until:
            return False

        return True

    def can_handle(self, specialty: TradeSpecialty) -> bool:
        """Check if technician can handle a specific specialty."""
        return specialty in self.specialties

    def has_certification(self, cert: CertificationType) -> bool:
        """Check if technician has a specific certification."""
        return cert in self.certifications

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "name": self.name,
            "phone": self.phone,
            "email": self.email,
            "qualification": self.qualification.value,
            "specialties": [s.value for s in self.specialties],
            "certifications": [c.value for c in self.certifications],
            "skills": self.skills,
            "years_experience": self.years_experience,
            "is_available": self.is_available,
            "remaining_capacity_minutes": self.remaining_capacity_minutes,
            "is_on_emergency_duty": self.is_on_emergency_duty,
        }


@dataclass
class JobRequirements:
    """Requirements for a job to match technicians."""

    specialty: TradeSpecialty
    required_certifications: list[CertificationType] = field(default_factory=list)
    min_qualification: TechnicianQualification = TechnicianQualification.GESELLE
    estimated_duration_minutes: int = 60
    is_emergency: bool = False
    requires_ladder: bool = False
    requires_drain_camera: bool = False
    customer_lat: float | None = None
    customer_lon: float | None = None


@dataclass
class TechnicianMatch:
    """Result of technician matching."""

    technician: Technician
    score: float  # 0-100
    estimated_travel_minutes: int | None = None
    match_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "technician": self.technician.to_dict(),
            "score": self.score,
            "estimated_travel_minutes": self.estimated_travel_minutes,
            "match_reasons": self.match_reasons,
            "warnings": self.warnings,
        }


class TechnicianMatcher:
    """Match jobs to best available technicians."""

    # Scoring weights
    WEIGHT_SKILLS = 0.40      # Skills and certifications match
    WEIGHT_AVAILABILITY = 0.25  # Current availability
    WEIGHT_WORKLOAD = 0.20    # Remaining capacity
    WEIGHT_DISTANCE = 0.15    # Travel distance

    def __init__(self, technicians: list[Technician] | None = None):
        """Initialize matcher with technician pool."""
        self._technicians = technicians or []

    def add_technician(self, technician: Technician):
        """Add a technician to the pool."""
        self._technicians.append(technician)

    def remove_technician(self, technician_id: UUID):
        """Remove a technician from the pool."""
        self._technicians = [
            t for t in self._technicians
            if t.id != technician_id
        ]

    def get_technician(self, technician_id: UUID) -> Technician | None:
        """Get a technician by ID."""
        for tech in self._technicians:
            if tech.id == technician_id:
                return tech
        return None

    def find_best_matches(
        self,
        requirements: JobRequirements,
        limit: int = 5,
    ) -> list[TechnicianMatch]:
        """
        Find best matching technicians for a job.

        Args:
            requirements: Job requirements
            limit: Maximum number of matches to return

        Returns:
            List of TechnicianMatch sorted by score (highest first)
        """
        matches: list[TechnicianMatch] = []

        for tech in self._technicians:
            match = self._score_technician(tech, requirements)
            if match.score > 0:
                matches.append(match)

        # Sort by score descending
        matches.sort(key=lambda m: m.score, reverse=True)

        return matches[:limit]

    def _score_technician(
        self,
        tech: Technician,
        req: JobRequirements,
    ) -> TechnicianMatch:
        """Score a technician against job requirements."""
        match_reasons: list[str] = []
        warnings: list[str] = []
        score = 0.0

        # 1. Skills match (40%)
        skills_score = 0.0

        # Check specialty
        if tech.can_handle(req.specialty):
            skills_score += 50
            match_reasons.append(f"Fachgebiet: {req.specialty.value}")
        else:
            warnings.append(f"Kein {req.specialty.value}-Fachmann")
            return TechnicianMatch(tech, 0, warnings=warnings)

        # Check certifications
        for cert in req.required_certifications:
            if tech.has_certification(cert):
                skills_score += 25
                match_reasons.append(f"Zertifizierung: {cert.value}")
            else:
                warnings.append(f"Fehlende Zertifizierung: {cert.value}")
                return TechnicianMatch(tech, 0, warnings=warnings)

        # Check qualification
        qualification_rank = {
            TechnicianQualification.HELFER: 1,
            TechnicianQualification.LEHRLING: 2,
            TechnicianQualification.FACHARBEITER: 3,
            TechnicianQualification.GESELLE: 4,
            TechnicianQualification.MEISTER: 5,
        }
        if qualification_rank[tech.qualification] >= qualification_rank[req.min_qualification]:
            skills_score += 25
            match_reasons.append(f"Qualifikation: {tech.qualification.value}")
        else:
            warnings.append("Qualifikation zu niedrig")
            return TechnicianMatch(tech, 0, warnings=warnings)

        # Check equipment
        if req.requires_ladder and not tech.has_ladder:
            warnings.append("Keine Leiter verfügbar")
        if req.requires_drain_camera and not tech.has_drain_camera:
            warnings.append("Keine Rohrkamera verfügbar")

        # Experience bonus
        if tech.years_experience >= 10:
            skills_score += 10
            match_reasons.append(f"{tech.years_experience} Jahre Erfahrung")
        elif tech.years_experience >= 5:
            skills_score += 5

        score += (skills_score / 100) * self.WEIGHT_SKILLS * 100

        # 2. Availability (25%)
        availability_score = 0.0

        if not tech.is_active:
            return TechnicianMatch(tech, 0, warnings=["Nicht aktiv"])

        if req.is_emergency:
            if tech.is_on_emergency_duty:
                availability_score = 100
                match_reasons.append("Notdienst aktiv")
            elif tech.is_available:
                availability_score = 50
            else:
                return TechnicianMatch(tech, 0, warnings=["Nicht verfügbar für Notfall"])
        else:
            if tech.is_available:
                availability_score = 100
                match_reasons.append("Sofort verfügbar")
            elif tech.available_from:
                hours_until = (tech.available_from - datetime.now()).total_seconds() / 3600
                if hours_until < 4:
                    availability_score = 50
                    match_reasons.append(f"Verfügbar in {int(hours_until)}h")

        score += (availability_score / 100) * self.WEIGHT_AVAILABILITY * 100

        # 3. Workload capacity (20%)
        workload_score = 0.0

        if tech.remaining_capacity_minutes >= req.estimated_duration_minutes:
            # Full capacity available
            capacity_ratio = tech.remaining_capacity_minutes / tech.max_workload_minutes
            workload_score = capacity_ratio * 100
            if capacity_ratio > 0.5:
                match_reasons.append(f"{int(capacity_ratio * 100)}% Kapazität frei")
        else:
            warnings.append("Nicht genug Zeit heute")
            workload_score = 20  # Partial score, might extend day

        score += (workload_score / 100) * self.WEIGHT_WORKLOAD * 100

        # 4. Distance (15%)
        distance_score = 100.0
        estimated_travel = None

        if req.customer_lat and req.customer_lon:
            if tech.current_lat and tech.current_lon:
                # Use current location
                distance = self._calculate_distance(
                    tech.current_lat, tech.current_lon,
                    req.customer_lat, req.customer_lon,
                )
            elif tech.home_base_lat and tech.home_base_lon:
                # Use home base
                distance = self._calculate_distance(
                    tech.home_base_lat, tech.home_base_lon,
                    req.customer_lat, req.customer_lon,
                )
            else:
                distance = None

            if distance is not None:
                if distance > tech.max_travel_radius_km:
                    warnings.append(f"Außerhalb Radius ({distance:.1f}km)")
                    distance_score = 0
                else:
                    # Score inversely proportional to distance
                    distance_score = max(0, 100 - (distance / tech.max_travel_radius_km * 100))
                    estimated_travel = int(distance * 2)  # Rough estimate: 2 min/km
                    if distance < 5:
                        match_reasons.append(f"Nur {distance:.1f}km entfernt")

        score += (distance_score / 100) * self.WEIGHT_DISTANCE * 100

        return TechnicianMatch(
            technician=tech,
            score=round(score, 1),
            estimated_travel_minutes=estimated_travel,
            match_reasons=match_reasons,
            warnings=warnings,
        )

    def _calculate_distance(
        self,
        lat1: float, lon1: float,
        lat2: float, lon2: float,
    ) -> float:
        """Calculate distance between two points in km (Haversine formula)."""
        from math import radians, sin, cos, sqrt, atan2

        R = 6371  # Earth's radius in km

        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])

        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))

        return R * c

    def get_available_technicians(
        self,
        specialty: TradeSpecialty | None = None,
    ) -> list[Technician]:
        """Get list of currently available technicians."""
        available = [t for t in self._technicians if t.is_available]

        if specialty:
            available = [t for t in available if t.can_handle(specialty)]

        return available

    def get_emergency_technicians(self) -> list[Technician]:
        """Get technicians on emergency duty."""
        return [
            t for t in self._technicians
            if t.is_on_emergency_duty and t.is_active
        ]


class MockTechnicianPool:
    """Mock technician pool for development/testing."""

    def __init__(self):
        """Initialize with sample technicians."""
        self.technicians = self._create_sample_technicians()

    def _create_sample_technicians(self) -> list[Technician]:
        """Create sample technicians."""
        return [
            Technician(
                id=uuid4(),
                name="Hans Müller",
                phone="+49 170 1111111",
                email="mueller@handwerk.de",
                qualification=TechnicianQualification.MEISTER,
                specialties=[TradeSpecialty.SHK],
                certifications=[CertificationType.GAS_BERECHTIGUNG],
                skills=["Heizungswartung", "Badsanierung", "Rohrreinigung"],
                years_experience=15,
                max_travel_radius_km=25,
                home_base_lat=52.5200,
                home_base_lon=13.4050,
                is_on_emergency_duty=True,
            ),
            Technician(
                id=uuid4(),
                name="Peter Schmidt",
                phone="+49 170 2222222",
                qualification=TechnicianQualification.GESELLE,
                specialties=[TradeSpecialty.SHK, TradeSpecialty.KLIMA],
                certifications=[CertificationType.KAELTEMITTEL],
                skills=["Klimaanlagen", "Wärmepumpen"],
                years_experience=8,
                max_travel_radius_km=30,
                home_base_lat=52.5100,
                home_base_lon=13.3900,
            ),
            Technician(
                id=uuid4(),
                name="Thomas Weber",
                phone="+49 170 3333333",
                qualification=TechnicianQualification.MEISTER,
                specialties=[TradeSpecialty.ELEKTRO],
                certifications=[CertificationType.ELEKTRO_BERECHTIGUNG],
                skills=["Elektroinstallation", "Smart Home", "Photovoltaik"],
                years_experience=20,
                max_travel_radius_km=35,
                home_base_lat=52.5300,
                home_base_lon=13.4200,
            ),
            Technician(
                id=uuid4(),
                name="Michael Becker",
                phone="+49 170 4444444",
                qualification=TechnicianQualification.GESELLE,
                specialties=[TradeSpecialty.SCHLOSSER],
                skills=["Türöffnung", "Schließanlagen", "Tresore"],
                years_experience=5,
                max_travel_radius_km=40,
                home_base_lat=52.4900,
                home_base_lon=13.4100,
                is_on_emergency_duty=True,
            ),
            Technician(
                id=uuid4(),
                name="Andreas Koch",
                phone="+49 170 5555555",
                qualification=TechnicianQualification.FACHARBEITER,
                specialties=[TradeSpecialty.MALER, TradeSpecialty.BAU],
                skills=["Innenanstrich", "Tapezieren", "Trockenbau"],
                years_experience=6,
                max_travel_radius_km=20,
                home_base_lat=52.5000,
                home_base_lon=13.4300,
            ),
        ]

    def get_matcher(self) -> TechnicianMatcher:
        """Get a matcher with the sample technicians."""
        return TechnicianMatcher(self.technicians.copy())


# Singleton instances
_technician_matcher: TechnicianMatcher | None = None


def get_technician_matcher() -> TechnicianMatcher:
    """Get or create technician matcher singleton with mock data."""
    global _technician_matcher
    if _technician_matcher is None:
        pool = MockTechnicianPool()
        _technician_matcher = pool.get_matcher()
    return _technician_matcher
