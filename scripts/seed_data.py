#!/usr/bin/env python3
"""Database seeding script for Phone Agent.

Generates realistic test data for development and testing.
Run with: python scripts/seed_data.py

Usage:
    python scripts/seed_data.py              # Seed all data
    python scripts/seed_data.py --contacts   # Seed only contacts
    python scripts/seed_data.py --calls      # Seed only calls
    python scripts/seed_data.py --clear      # Clear all data first
"""
from __future__ import annotations

import asyncio
import os
import random
import sys
from datetime import date, time, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Set database URL if not set
if "ITF_DATABASE_URL" not in os.environ:
    os.environ["ITF_DATABASE_URL"] = "sqlite+aiosqlite:///./phone_agent.db"

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from phone_agent.db.base import Base
from phone_agent.db.models import (
    CallModel,
    AppointmentModel,
    ContactModel,
    CompanyModel,
    CallMetricsModel,
    RecallCampaignModel,
)


# ============================================================================
# Sample Data
# ============================================================================

GERMAN_FIRST_NAMES = [
    "Max", "Anna", "Paul", "Maria", "Felix", "Sophie", "Leon", "Emma",
    "Lukas", "Mia", "Jonas", "Hannah", "Elias", "Lena", "Noah", "Lea",
    "Tim", "Laura", "Finn", "Lisa", "Niklas", "Julia", "David", "Sarah",
    "Jan", "Nina", "Moritz", "Johanna", "Philipp", "Katharina",
]

GERMAN_LAST_NAMES = [
    "Müller", "Schmidt", "Schneider", "Fischer", "Weber", "Meyer", "Wagner",
    "Becker", "Schulz", "Hoffmann", "Koch", "Bauer", "Richter", "Klein",
    "Wolf", "Schröder", "Neumann", "Schwarz", "Zimmermann", "Braun",
    "Krüger", "Hartmann", "Lange", "Werner", "Krause", "Meier", "Lehmann",
]

GERMAN_CITIES = [
    ("Berlin", "10115", "Berlin"),
    ("Hamburg", "20095", "Hamburg"),
    ("München", "80331", "Bayern"),
    ("Köln", "50667", "Nordrhein-Westfalen"),
    ("Frankfurt", "60311", "Hessen"),
    ("Stuttgart", "70173", "Baden-Württemberg"),
    ("Düsseldorf", "40213", "Nordrhein-Westfalen"),
    ("Leipzig", "04109", "Sachsen"),
    ("Dortmund", "44135", "Nordrhein-Westfalen"),
    ("Essen", "45127", "Nordrhein-Westfalen"),
    ("Bremen", "28195", "Bremen"),
    ("Dresden", "01067", "Sachsen"),
    ("Hannover", "30159", "Niedersachsen"),
    ("Nürnberg", "90402", "Bayern"),
]

STREET_NAMES = [
    "Hauptstraße", "Bahnhofstraße", "Berliner Straße", "Gartenstraße",
    "Lindenstraße", "Kirchstraße", "Schulstraße", "Friedrichstraße",
    "Bismarckstraße", "Goethestraße", "Schillerstraße", "Parkstraße",
]

APPOINTMENT_TYPES_HEALTH = [
    "consultation", "checkup", "followup", "vaccination", "blood_test",
    "x_ray", "ultrasound", "therapy", "prescription",
]

APPOINTMENT_TYPES_HANDWERK = [
    "estimate", "repair", "installation", "maintenance", "consultation",
]

PROVIDER_NAMES = [
    "Dr. Müller", "Dr. Schmidt", "Dr. Weber", "Dr. Fischer",
    "Dr. Becker", "Dr. Hoffmann", "Dr. Richter",
]

COMPANY_NAMES = [
    "Müller & Söhne GmbH", "Schmidt Handwerk", "Weber Elektro",
    "Fischer Sanitär", "Becker Bau", "Hoffmann Immobilien",
    "Richter Consulting", "Klein & Partner", "Wolf IT-Services",
]

INDUSTRIES = ["gesundheit", "handwerk", "freie_berufe"]


def random_phone() -> str:
    """Generate a random German phone number."""
    prefix = random.choice(["+49", "0"])
    area = random.choice(["30", "40", "89", "221", "69", "711", "211"])
    number = "".join(str(random.randint(0, 9)) for _ in range(7))
    return f"{prefix}{area}{number}"


def random_email(first: str, last: str) -> str:
    """Generate a random email address."""
    domain = random.choice(["gmail.com", "web.de", "gmx.de", "t-online.de", "outlook.de"])
    return f"{first.lower()}.{last.lower()}@{domain}"


def random_date_between(start: date, end: date) -> date:
    """Generate a random date between start and end."""
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, delta))


def random_time() -> time:
    """Generate a random business hour time."""
    hour = random.randint(8, 17)
    minute = random.choice([0, 15, 30, 45])
    return time(hour, minute)


async def create_contacts(session: AsyncSession, count: int = 100) -> list[ContactModel]:
    """Create sample contacts."""
    print(f"Creating {count} contacts...")
    contacts = []

    for i in range(count):
        first = random.choice(GERMAN_FIRST_NAMES)
        last = random.choice(GERMAN_LAST_NAMES)
        city, zip_code, _ = random.choice(GERMAN_CITIES)
        industry = random.choice(INDUSTRIES)

        contact_type = "patient" if industry == "gesundheit" else "customer"

        contact = ContactModel(
            id=uuid4(),
            first_name=first,
            last_name=last,
            phone_primary=random_phone(),
            phone_mobile=random_phone() if random.random() > 0.5 else None,
            email=random_email(first, last) if random.random() > 0.3 else None,
            street=random.choice(STREET_NAMES),
            street_number=str(random.randint(1, 200)),
            zip_code=zip_code,
            city=city,
            country="Germany",
            contact_type=contact_type,
            industry=industry,
            source=random.choice(["phone", "web", "referral", "walk_in"]),
            preferred_language="de",
            total_calls=random.randint(0, 20),
            total_appointments=random.randint(0, 10),
            total_no_shows=random.randint(0, 2),
        )

        # Add health-specific fields
        if industry == "gesundheit":
            contact.date_of_birth = random_date_between(
                date(1950, 1, 1), date(2005, 1, 1)
            )
            contact.insurance_type = random.choice(["gesetzlich", "privat"])

        session.add(contact)
        contacts.append(contact)

        if (i + 1) % 25 == 0:
            print(f"  Created {i + 1} contacts...")

    await session.commit()
    print(f"✓ Created {count} contacts")
    return contacts


async def create_companies(session: AsyncSession, count: int = 20) -> list[CompanyModel]:
    """Create sample companies."""
    print(f"Creating {count} companies...")
    companies = []

    for i in range(count):
        city, zip_code, _ = random.choice(GERMAN_CITIES)

        company = CompanyModel(
            id=uuid4(),
            name=random.choice(COMPANY_NAMES) + f" {i+1}",
            industry=random.choice(INDUSTRIES),
            phone=random_phone(),
            email=f"info@company{i+1}.de" if random.random() > 0.3 else None,
            website=f"https://www.company{i+1}.de" if random.random() > 0.5 else None,
            street=random.choice(STREET_NAMES),
            street_number=str(random.randint(1, 200)),
            zip_code=zip_code,
            city=city,
            country="Germany",
            size=random.choice(["small", "medium", "large"]) if random.random() > 0.5 else None,
        )

        session.add(company)
        companies.append(company)

    await session.commit()
    print(f"✓ Created {count} companies")
    return companies


async def create_calls(
    session: AsyncSession,
    contacts: list[ContactModel],
    days: int = 30,
    calls_per_day: int = 20,
) -> list[CallModel]:
    """Create sample calls."""
    total_calls = days * calls_per_day
    print(f"Creating ~{total_calls} calls over {days} days...")
    calls = []

    end_date = date.today()
    start_date = end_date - timedelta(days=days)

    for day_offset in range(days):
        current_date = start_date + timedelta(days=day_offset)
        daily_calls = random.randint(calls_per_day - 5, calls_per_day + 5)

        for _ in range(daily_calls):
            contact = random.choice(contacts)
            direction = random.choice(["inbound", "inbound", "inbound", "outbound"])
            status = random.choices(
                ["completed", "missed", "failed"],
                weights=[80, 15, 5],
            )[0]

            started_at = datetime.combine(
                current_date,
                random_time(),
                tzinfo=timezone.utc,
            )

            duration = random.randint(30, 600) if status == "completed" else None

            call = CallModel(
                id=uuid4(),
                direction=direction,
                status=status,
                caller_id=contact.phone_primary if direction == "inbound" else "+4930123456",
                callee_id="+4930123456" if direction == "inbound" else contact.phone_primary,
                started_at=started_at,
                ended_at=started_at + timedelta(seconds=duration) if duration else None,
                duration_seconds=duration,
                contact_id=str(contact.id),
                triage_result=random.choice(["routine", "urgent", "emergency"]) if status == "completed" else None,
                transferred=random.random() > 0.9,
                summary=f"Call with {contact.first_name} {contact.last_name}" if status == "completed" else None,
            )

            session.add(call)
            calls.append(call)

        if (day_offset + 1) % 7 == 0:
            await session.commit()
            print(f"  Created calls for {day_offset + 1} days...")

    await session.commit()
    print(f"✓ Created {len(calls)} calls")
    return calls


async def create_appointments(
    session: AsyncSession,
    contacts: list[ContactModel],
    days_back: int = 14,
    days_forward: int = 30,
    appointments_per_day: int = 15,
) -> list[AppointmentModel]:
    """Create sample appointments."""
    total_days = days_back + days_forward
    print(f"Creating ~{total_days * appointments_per_day} appointments...")
    appointments = []

    today = date.today()
    start_date = today - timedelta(days=days_back)
    end_date = today + timedelta(days=days_forward)

    current_date = start_date
    while current_date <= end_date:
        # Skip weekends
        if current_date.weekday() >= 5:
            current_date += timedelta(days=1)
            continue

        daily_count = random.randint(appointments_per_day - 5, appointments_per_day + 5)

        for _ in range(daily_count):
            contact = random.choice(contacts)

            # Determine status based on date
            if current_date < today:
                status = random.choices(
                    ["completed", "no_show", "cancelled"],
                    weights=[85, 10, 5],
                )[0]
            elif current_date == today:
                status = random.choice(["scheduled", "confirmed", "completed"])
            else:
                status = random.choice(["scheduled", "confirmed"])

            apt_type = (
                random.choice(APPOINTMENT_TYPES_HEALTH)
                if contact.industry == "gesundheit"
                else random.choice(APPOINTMENT_TYPES_HANDWERK)
            )

            appointment = AppointmentModel(
                id=uuid4(),
                patient_name=f"{contact.first_name} {contact.last_name}",
                patient_phone=contact.phone_primary,
                patient_email=contact.email,
                appointment_date=current_date,
                appointment_time=random_time(),
                duration_minutes=random.choice([15, 30, 45, 60]),
                type=apt_type,
                status=status,
                provider_name=random.choice(PROVIDER_NAMES) if contact.industry == "gesundheit" else None,
                contact_id=str(contact.id),
                reminder_sent=current_date < today or (current_date == today and random.random() > 0.3),
                confirmed=status == "confirmed" or (current_date < today and status == "completed"),
                created_by=random.choice(["phone_agent", "web", "manual"]),
            )

            session.add(appointment)
            appointments.append(appointment)

        current_date += timedelta(days=1)

    await session.commit()
    print(f"✓ Created {len(appointments)} appointments")
    return appointments


async def create_call_metrics(
    session: AsyncSession,
    days: int = 30,
) -> list[CallMetricsModel]:
    """Create sample call metrics."""
    print(f"Creating call metrics for {days} days...")
    metrics = []

    end_date = date.today()
    start_date = end_date - timedelta(days=days)

    current_date = start_date
    while current_date <= end_date:
        # Daily aggregated metrics
        total = random.randint(50, 150)
        inbound = int(total * random.uniform(0.7, 0.85))
        outbound = total - inbound
        completed = int(total * random.uniform(0.75, 0.90))
        missed = int(total * random.uniform(0.05, 0.15))
        failed = total - completed - missed

        metric = CallMetricsModel(
            id=uuid4(),
            date=current_date,
            hour=None,  # Daily aggregate
            industry="gesundheit",
            total_calls=total,
            inbound_calls=inbound,
            outbound_calls=outbound,
            completed_calls=completed,
            missed_calls=missed,
            failed_calls=failed,
            transferred_calls=random.randint(2, 15),
            total_duration=completed * random.randint(120, 300),
            avg_duration=random.uniform(120, 300),
            min_duration=random.randint(15, 60),
            max_duration=random.randint(600, 1200),
            avg_wait_time=random.uniform(5, 30),
            max_wait_time=random.randint(60, 300),
            appointments_booked=random.randint(20, 60),
            appointments_modified=random.randint(5, 20),
            appointments_cancelled=random.randint(2, 10),
            service_calls_created=0,
            quotes_sent=0,
            ai_handled_calls=int(completed * random.uniform(0.85, 0.95)),
            human_escalations=random.randint(2, 15),
            completion_rate=completed / total if total else 0,
            appointment_conversion_rate=random.uniform(0.3, 0.6),
            ai_resolution_rate=random.uniform(0.85, 0.95),
        )

        session.add(metric)
        metrics.append(metric)

        current_date += timedelta(days=1)

    await session.commit()
    print(f"✓ Created {len(metrics)} call metrics records")
    return metrics


async def create_campaigns(session: AsyncSession, count: int = 5) -> list[RecallCampaignModel]:
    """Create sample recall campaigns."""
    print(f"Creating {count} recall campaigns...")
    campaigns = []

    campaign_types = ["recall", "reminder", "promotion", "survey"]
    statuses = ["draft", "scheduled", "active", "paused", "completed"]

    for i in range(count):
        start_date = date.today() - timedelta(days=random.randint(0, 60))

        campaign = RecallCampaignModel(
            id=uuid4(),
            name=f"Campaign {i+1}: {random.choice(['Vorsorge', 'Impfung', 'Nachsorge', 'Recall'])}",
            description=f"Test campaign {i+1} for development",
            campaign_type=random.choice(campaign_types),
            status=random.choice(statuses),
            industry="gesundheit",
            start_date=start_date,
            end_date=start_date + timedelta(days=random.randint(7, 30)),
            total_contacts=random.randint(50, 500),
            contacts_called=random.randint(0, 300),
            contacts_reached=random.randint(0, 200),
            appointments_booked=random.randint(0, 50),
            priority=random.randint(1, 5),
        )

        session.add(campaign)
        campaigns.append(campaign)

    await session.commit()
    print(f"✓ Created {count} campaigns")
    return campaigns


async def clear_all_data(session: AsyncSession) -> None:
    """Clear all data from tables."""
    print("Clearing existing data...")

    tables = [
        "appointments", "calls", "call_metrics", "campaign_metrics",
        "recall_campaigns", "consents", "audit_logs", "contact_company_links",
        "contacts", "companies", "dashboard_snapshots", "data_retention_policies",
    ]

    for table in tables:
        try:
            await session.execute(text(f"DELETE FROM {table}"))
            print(f"  Cleared {table}")
        except Exception as e:
            print(f"  Warning: Could not clear {table}: {e}")

    await session.commit()
    print("✓ Data cleared")


async def main():
    """Run the seeding script."""
    import argparse

    parser = argparse.ArgumentParser(description="Seed the Phone Agent database")
    parser.add_argument("--clear", action="store_true", help="Clear all data first")
    parser.add_argument("--contacts", action="store_true", help="Seed only contacts")
    parser.add_argument("--calls", action="store_true", help="Seed only calls")
    parser.add_argument("--appointments", action="store_true", help="Seed only appointments")
    parser.add_argument("--metrics", action="store_true", help="Seed only metrics")
    parser.add_argument("--campaigns", action="store_true", help="Seed only campaigns")
    parser.add_argument("--all", action="store_true", help="Seed all data (default)")

    args = parser.parse_args()

    # Default to seeding all if no specific option given
    seed_all = args.all or not any([
        args.contacts, args.calls, args.appointments, args.metrics, args.campaigns
    ])

    # Create async engine
    database_url = os.environ.get("ITF_DATABASE_URL", "sqlite+aiosqlite:///./phone_agent.db")
    print(f"Database: {database_url}")

    engine = create_async_engine(database_url, echo=False)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        if args.clear:
            await clear_all_data(session)

        contacts = []

        if seed_all or args.contacts:
            contacts = await create_contacts(session, count=100)

        if seed_all or args.calls:
            if not contacts:
                # Load existing contacts
                from sqlalchemy import select
                result = await session.execute(select(ContactModel))
                contacts = list(result.scalars().all())
            if contacts:
                await create_calls(session, contacts, days=30, calls_per_day=25)
            else:
                print("Warning: No contacts found for calls")

        if seed_all or args.appointments:
            if not contacts:
                from sqlalchemy import select
                result = await session.execute(select(ContactModel))
                contacts = list(result.scalars().all())
            if contacts:
                await create_appointments(session, contacts)
            else:
                print("Warning: No contacts found for appointments")

        if seed_all or args.metrics:
            await create_call_metrics(session, days=60)

        if seed_all or args.campaigns:
            await create_campaigns(session, count=10)

        if seed_all:
            await create_companies(session, count=20)

    await engine.dispose()
    print("\n✓ Seeding complete!")


if __name__ == "__main__":
    asyncio.run(main())
