"""Response generation for healthcare conversations.

Provides German language response templates and formatting.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from phone_agent.industry.gesundheit.scheduling import TimeSlot


def get_time_greeting() -> str:
    """Get time-appropriate greeting in German."""
    hour = datetime.now().hour
    if hour < 12:
        return "Guten Morgen"
    elif hour < 18:
        return "Guten Tag"
    else:
        return "Guten Abend"


def greeting(practice_name: str) -> str:
    """Generate greeting message."""
    time_greeting = get_time_greeting()
    return (
        f"{time_greeting}, Praxis {practice_name}, "
        f"hier spricht der Telefonassistent. "
        f"Wie kann ich Ihnen helfen?"
    )


def farewell(practice_name: str) -> str:
    """Generate farewell message."""
    return (
        f"Vielen Dank für Ihren Anruf bei der Praxis {practice_name}. "
        f"Auf Wiederhören!"
    )


def emergency_warning() -> str:
    """Generate emergency warning message."""
    return (
        "Ich verstehe, dass Sie dringende Beschwerden haben. "
        "Bei lebensbedrohlichen Symptomen wie Brustschmerzen, "
        "schwerer Atemnot oder Bewusstlosigkeit rufen Sie bitte "
        "sofort die 112 an. "
        "Soll ich Sie mit unserem medizinischen Personal verbinden?"
    )


def transfer_message() -> str:
    """Generate transfer to staff message."""
    return (
        "Ich verbinde Sie mit unserem Praxisteam. "
        "Bitte bleiben Sie einen Moment in der Leitung."
    )


def not_understood() -> str:
    """Generate not understood message."""
    return (
        "Entschuldigung, das habe ich nicht verstanden. "
        "Möchten Sie einen Termin vereinbaren, einen bestehenden "
        "Termin ändern, oder mit unserem Praxisteam sprechen?"
    )


def request_identification(context: str = "booking") -> str:
    """Generate patient identification request.

    Args:
        context: Reason for identification (booking, prescription, lab, reschedule)
    """
    prompts = {
        "booking": (
            "Gerne helfe ich Ihnen dabei. "
            "Darf ich kurz Ihren Namen und Ihr Geburtsdatum für unsere Unterlagen haben?"
        ),
        "prescription": (
            "Für Rezeptanfragen melde ich Sie gerne vor. "
            "Darf ich Ihren Namen und Ihr Geburtsdatum haben?"
        ),
        "lab": (
            "Für Laborergebnisse muss ich kurz Ihre Identität überprüfen. "
            "Darf ich Ihren Namen und Ihr Geburtsdatum haben?"
        ),
        "reschedule": (
            "Ich helfe Ihnen gerne beim Umbuchen Ihres Termins. "
            "Darf ich Ihren Namen und Ihr Geburtsdatum haben, damit ich Ihren Termin finde?"
        ),
        "cancel": (
            "Das tut mir leid zu hören. Ich storniere Ihren Termin gerne. "
            "Darf ich Ihren Namen und Ihr Geburtsdatum haben?"
        ),
    }
    return prompts.get(context, prompts["booking"])


def ask_reason(first_name: str) -> str:
    """Ask for reason of call."""
    return f"Vielen Dank. Was ist der Grund Ihres Anrufs, {first_name}?"


def prescription_medication_request(first_name: str) -> str:
    """Ask for prescription medication details."""
    return (
        f"Vielen Dank, {first_name}. Welches Medikament möchten Sie nachbestellen? "
        f"Und von wann war Ihr letztes Rezept?"
    )


def prescription_pharmacy_request(medication: str) -> str:
    """Ask for pharmacy preference."""
    return (
        f"Verstanden, Sie möchten {medication} nachbestellen. "
        f"Von welcher Apotheke soll das Rezept abgeholt werden? "
        f"Oder möchten Sie es in der Praxis abholen?"
    )


def prescription_confirmed(first_name: str, medication: str, pharmacy: str) -> str:
    """Confirm prescription request."""
    return (
        f"Perfekt, {first_name}! Ich habe Ihre Rezeptanfrage notiert:\n"
        f"- Medikament: {medication}\n"
        f"- Abholung: {pharmacy}\n\n"
        f"Das Rezept wird zur Prüfung an den Arzt weitergeleitet. "
        f"Sie erhalten eine Benachrichtigung, wenn es bereit ist. "
        f"Kann ich sonst noch etwas für Sie tun?"
    )


def lab_dob_verification(first_name: str) -> str:
    """Request DOB for lab results verification."""
    return (
        f"Vielen Dank, {first_name}. Zur Sicherheit: "
        f"Können Sie mir bitte Ihr vollständiges Geburtsdatum nennen?"
    )


def lab_results_ready(first_name: str) -> str:
    """Inform about ready lab results."""
    return (
        f"Vielen Dank, {first_name}. Ihre Identität ist bestätigt. "
        f"Ihre Laborergebnisse liegen vor. "
        f"Der Arzt möchte diese gerne mit Ihnen persönlich besprechen. "
        f"Soll ich Ihnen einen Besprechungstermin vorschlagen?"
    )


def lab_results_not_ready(first_name: str) -> str:
    """Inform lab results not ready."""
    return (
        f"Vielen Dank, {first_name}. Ihre Laborergebnisse liegen leider noch nicht vor. "
        f"Sobald sie da sind, werden Sie benachrichtigt. "
        f"Kann ich sonst noch etwas für Sie tun?"
    )


def reschedule_lookup(first_name: str) -> str:
    """Ask about current appointment for reschedule."""
    return (
        f"Vielen Dank, {first_name}. Ich schaue nach Ihrem Termin. "
        f"Können Sie mir sagen, wann Ihr aktueller Termin ist?"
    )


def cancel_reason_request(first_name: str) -> str:
    """Ask for cancellation reason."""
    return (
        f"Ich habe Ihren Termin gefunden, {first_name}. "
        f"Darf ich fragen, warum Sie den Termin absagen möchten? "
        f"Das hilft uns bei der Planung."
    )


def cancel_confirmed(first_name: str) -> str:
    """Confirm appointment cancellation."""
    return (
        f"Ihr Termin wurde storniert, {first_name}. "
        f"Vielen Dank für die Absage. "
        f"Möchten Sie gleich einen neuen Termin vereinbaren?"
    )


def no_slots_available() -> str:
    """No appointment slots available message."""
    return (
        "Leider habe ich aktuell keine passenden Termine gefunden. "
        "Soll ich Sie für einen Rückruf vormerken?"
    )


def appointment_selection_prompt() -> str:
    """Ask for appointment selection."""
    return "Welcher Termin passt Ihnen am besten?"


def appointment_selection_unclear() -> str:
    """Unclear appointment selection."""
    return "Entschuldigung, welche Option möchten Sie? Bitte sagen Sie Option 1, 2 oder 3."


def appointment_confirm_prompt(slot_text: str) -> str:
    """Confirm appointment selection."""
    return f"Perfekt! Ich trage Sie ein für {slot_text}. Ist das so richtig?"


def appointment_booked(slot_text: str) -> str:
    """Appointment booked confirmation."""
    return (
        f"Wunderbar! Ihr Termin ist bestätigt für {slot_text}. "
        f"Bitte bringen Sie Ihre Versichertenkarte mit. "
        f"Kann ich sonst noch etwas für Sie tun?"
    )


def appointment_rescheduled(slot_text: str) -> str:
    """Appointment rescheduled confirmation."""
    return (
        f"Perfekt! Ihr Termin wurde umgebucht auf {slot_text}. "
        f"Bitte bringen Sie Ihre Versichertenkarte mit. "
        f"Kann ich sonst noch etwas für Sie tun?"
    )


def triage_urgent(recommendation: str) -> str:
    """Urgent triage result message."""
    return (
        f"Ich verstehe. {recommendation} "
        f"Ich suche Ihnen sofort einen Termin."
    )


def triage_normal(recommendation: str) -> str:
    """Normal triage result message."""
    return (
        f"Vielen Dank für die Information. {recommendation} "
        f"Ich schaue nach verfügbaren Terminen."
    )


def sms_confirmation(practice_name: str, slot_text: str) -> str:
    """SMS confirmation text."""
    return f"Praxis {practice_name}: Termin bestätigt für {slot_text}."


def sms_reschedule(practice_name: str, slot_text: str) -> str:
    """SMS reschedule confirmation text."""
    return f"Praxis {practice_name}: Termin umgebucht auf {slot_text}."


def sms_cancellation(practice_name: str) -> str:
    """SMS cancellation confirmation text."""
    return f"Praxis {practice_name}: Ihr Termin wurde storniert."
