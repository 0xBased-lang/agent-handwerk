"""German prompts for outbound healthcare calls.

All prompts are in professional, friendly German appropriate
for medical practice phone calls.

Includes prompts for:
- Appointment reminders
- Recall campaigns (Vorsorge, Impfungen, DMP)
- No-show follow-up
"""
from __future__ import annotations

from typing import Any


# ============ SYSTEM PROMPTS ============

OUTBOUND_SYSTEM_PROMPT = """Du bist ein professioneller Telefonassistent einer deutschen Arztpraxis.
Deine Aufgabe ist es, Patienten freundlich und respektvoll anzurufen.

Wichtige Verhaltensregeln:
- Sprich immer höflich mit "Sie"
- Stelle dich zuerst vor und nenne die Praxis
- Erkläre klar den Grund deines Anrufs
- Respektiere, wenn Patienten nicht sprechen können oder wollen
- Biete immer Alternativen an (SMS, Rückruf)
- Bestätige wichtige Informationen durch Wiederholung
- Verabschiede dich höflich

Bei Unsicherheiten:
- Biete an, dass ein Mitarbeiter zurückruft
- Gib die Praxistelefonnummer für Rückfragen
- Dokumentiere alle wichtigen Informationen
"""


# ============ APPOINTMENT REMINDER PROMPTS ============

REMINDER_INTRODUCTION = """Guten {time_greeting}, hier spricht der Telefonassistent der Praxis {practice_name}.
Spreche ich mit {patient_name}?"""

REMINDER_PURPOSE = """Ich rufe an, um Sie an Ihren Termin zu erinnern.
Sie haben einen Termin am {appointment_date} um {appointment_time} Uhr bei {provider_name}.
Können Sie diesen Termin wahrnehmen?"""

REMINDER_CONFIRM_SUCCESS = """Wunderbar! Ich habe Ihren Termin als bestätigt markiert.
Bitte denken Sie daran, Ihre Versichertenkarte mitzubringen.
Wir freuen uns auf Ihren Besuch!"""

REMINDER_RESCHEDULE_OFFER = """Kein Problem. Soll ich Ihnen einen anderen Termin anbieten?
Ich kann Ihnen folgende Alternativen vorschlagen:
{slot_options}
Welcher Termin passt Ihnen besser?"""

REMINDER_RESCHEDULE_SUCCESS = """Perfekt! Ich habe Ihren Termin umgebucht auf {new_slot}.
Sie erhalten gleich eine SMS-Bestätigung.
Auf Wiederhören!"""

REMINDER_CANCEL_CONFIRM = """Ich habe Ihren Termin storniert.
Möchten Sie zu einem späteren Zeitpunkt einen neuen Termin vereinbaren?"""

REMINDER_VOICEMAIL = """Guten {time_greeting}, hier ist ein automatischer Anruf der Praxis {practice_name}.
Wir möchten Sie an Ihren Termin am {appointment_date} um {appointment_time} Uhr erinnern.
Bitte rufen Sie uns unter {practice_phone} an, wenn Sie den Termin nicht wahrnehmen können.
Auf Wiederhören!"""

REMINDER_SMS_CONFIRM = """Praxis {practice_name}: Ihr Termin am {appointment_date} um {appointment_time} Uhr bei {provider_name} ist bestätigt. Bitte 10 Min. vorher da sein. Bei Verhinderung: {practice_phone}"""

REMINDER_SMS_FALLBACK = """Praxis {practice_name}: Terminerinnerung für {appointment_date} um {appointment_time} Uhr. Bestätigung/Absage unter {practice_phone}"""


# ============ RECALL CAMPAIGN PROMPTS ============

RECALL_INTRODUCTION_GENERAL = """Guten {time_greeting}, hier spricht der Telefonassistent der Praxis {practice_name}.
Spreche ich mit {patient_name}?"""

RECALL_PURPOSE_PREVENTIVE = """Ich rufe an, weil für Sie eine Vorsorgeuntersuchung ansteht.
Der Gesundheits-Check-up ist eine wichtige Untersuchung zur Früherkennung von Krankheiten.
Die Kosten werden von Ihrer Krankenkasse übernommen.
Darf ich Ihnen einen Termin vorschlagen?"""

RECALL_PURPOSE_VACCINATION = """Ich rufe an, um Sie zur {vaccination_type} einzuladen.
Die {vaccination_name} ist jetzt verfügbar und wird von den Krankenkassen übernommen.
Möchten Sie einen Impftermin vereinbaren?"""

RECALL_PURPOSE_VACCINATION_FLU = """Ich rufe an, um Sie zur Grippeimpfung einzuladen.
Die Grippesaison steht bevor und die Impfung ist der beste Schutz.
Die Kosten werden von Ihrer Krankenkasse übernommen.
Haben Sie Interesse an einem Impftermin?"""

RECALL_PURPOSE_VACCINATION_COVID = """Ich rufe an wegen Ihrer COVID-19-Auffrischungsimpfung.
Die Ständige Impfkommission empfiehlt eine regelmäßige Auffrischung.
Möchten Sie einen Termin vereinbaren?"""

RECALL_PURPOSE_DMP = """Ich rufe an wegen Ihrer DMP-Kontrolluntersuchung.
Ihre regelmäßige Kontrolle im Rahmen des Disease-Management-Programms steht an.
Diese Untersuchung ist wichtig für Ihre Gesundheit und wird von der Krankenkasse erwartet.
Wann passt es Ihnen am besten?"""

RECALL_PURPOSE_FOLLOWUP = """Ich rufe an, weil der Arzt Sie gerne zur Nachuntersuchung sehen möchte.
Es wäre wichtig, den Verlauf Ihrer Behandlung zu überprüfen.
Darf ich Ihnen einen Termin vorschlagen?"""

RECALL_PURPOSE_LAB_RESULTS = """Ich rufe an, weil Ihre Laborergebnisse vorliegen.
Der Arzt möchte diese gerne mit Ihnen besprechen.
Haben Sie Zeit für einen kurzen Besprechungstermin?"""

RECALL_SLOT_OFFER = """Ich kann Ihnen folgende Termine anbieten:
{slot_options}
Welcher Termin passt Ihnen am besten?"""

RECALL_SUCCESS = """Wunderbar! Ich habe Sie eingetragen für {appointment_slot}.
Sie erhalten gleich eine SMS-Bestätigung.
Vielen Dank und auf Wiederhören!"""

RECALL_DECLINED_POLITE = """Das verstehe ich. Darf ich Sie zu einem späteren Zeitpunkt nochmal kontaktieren?"""

RECALL_VOICEMAIL = """Guten {time_greeting}, hier ist ein Anruf der Praxis {practice_name}.
{purpose_message}
Bitte rufen Sie uns unter {practice_phone} zurück oder vereinbaren Sie online einen Termin.
Auf Wiederhören!"""


# ============ NO-SHOW FOLLOW-UP PROMPTS ============

NOSHOW_INTRODUCTION = """Guten {time_greeting}, hier spricht der Telefonassistent der Praxis {practice_name}.
Spreche ich mit {patient_name}?"""

NOSHOW_PURPOSE = """Ich rufe an, weil wir Sie am {missed_date} zum Termin erwartet hatten.
Wir hoffen, es geht Ihnen gut.
Ist alles in Ordnung bei Ihnen?"""

NOSHOW_EMPATHETIC_SICK = """Das tut mir leid zu hören, dass es Ihnen nicht gut geht.
Brauchen Sie einen neuen Termin, wenn es Ihnen besser geht?"""

NOSHOW_EMPATHETIC_FORGOT = """Das kann passieren. Keine Sorge.
Soll ich Ihnen gleich einen neuen Termin anbieten?"""

NOSHOW_EMPATHETIC_BARRIER = """Ich verstehe. Das ist natürlich schwierig.
Kann ich Ihnen vielleicht einen Termin zu einer anderen Zeit anbieten,
die besser für Sie passt?"""

NOSHOW_RESCHEDULE_OFFER = """Ich kann Ihnen folgende Termine anbieten:
{slot_options}
Welcher würde Ihnen passen?"""

NOSHOW_RESCHEDULE_SUCCESS = """Sehr gut! Ich habe Sie eingetragen für {new_slot}.
Sie erhalten eine SMS-Bestätigung.
Wir freuen uns auf Ihren Besuch!"""

NOSHOW_DECLINE_POLITE = """Das verstehe ich. Falls Sie später doch einen Termin brauchen,
können Sie uns jederzeit unter {practice_phone} erreichen.
Ich wünsche Ihnen alles Gute!"""

NOSHOW_TRANSFER_OFFER = """Wenn Sie möchten, kann ich Sie mit unserem Praxisteam verbinden.
Soll ich das tun?"""

NOSHOW_VOICEMAIL = """Guten {time_greeting}, hier ist die Praxis {practice_name}.
Wir hatten Sie am {missed_date} zum Termin erwartet und wollten nachfragen, ob alles in Ordnung ist.
Bitte rufen Sie uns unter {practice_phone} zurück, wenn Sie einen neuen Termin vereinbaren möchten.
Auf Wiederhören!"""


# ============ COMMON PHRASES ============

PHRASES = {
    # Identity verification
    "verify_identity": "Zur Sicherheit: Können Sie mir bitte Ihr Geburtsdatum nennen?",
    "identity_confirmed": "Vielen Dank, Ihre Identität ist bestätigt.",
    "identity_failed": "Die Angaben stimmen leider nicht überein. Ich verbinde Sie mit einem Mitarbeiter.",

    # Slot selection
    "slot_select_first": "Den ersten Termin",
    "slot_select_second": "Den zweiten Termin",
    "slot_select_third": "Den dritten Termin",
    "slot_select_other": "Keiner passt, andere Zeiten",

    # Confirmations
    "confirm_yes": "Ja, das ist richtig",
    "confirm_no": "Nein, das stimmt nicht",
    "understood": "Verstanden",
    "noted": "Ich habe es notiert",

    # Polite closings
    "farewell_standard": "Vielen Dank für Ihre Zeit. Auf Wiederhören!",
    "farewell_appointment": "Wir freuen uns auf Ihren Besuch. Auf Wiederhören!",
    "farewell_wellness": "Ich wünsche Ihnen gute Besserung. Auf Wiederhören!",

    # Time of day greetings
    "morning": "Guten Morgen",
    "afternoon": "Guten Tag",
    "evening": "Guten Abend",

    # Error handling
    "not_understood": "Entschuldigung, das habe ich nicht verstanden. Können Sie das bitte wiederholen?",
    "bad_connection": "Die Verbindung ist leider schlecht. Ich versuche es später nochmal.",
    "transfer_offer": "Möchten Sie lieber mit einem Mitarbeiter sprechen?",

    # Waiting
    "please_wait": "Einen Moment bitte.",
    "searching": "Ich schaue nach verfügbaren Terminen.",
    "processing": "Ich trage das ein.",
}


# ============ HELPER FUNCTIONS ============

def get_time_greeting() -> str:
    """Get time-appropriate greeting."""
    from datetime import datetime
    hour = datetime.now().hour
    if hour < 12:
        return PHRASES["morning"]
    elif hour < 18:
        return PHRASES["afternoon"]
    else:
        return PHRASES["evening"]


def format_reminder_prompt(
    template: str,
    patient_name: str,
    practice_name: str,
    appointment_date: str,
    appointment_time: str,
    provider_name: str,
    practice_phone: str = "",
    **kwargs: Any,
) -> str:
    """Format a reminder prompt with patient and appointment details."""
    return template.format(
        time_greeting=get_time_greeting().lower(),
        patient_name=patient_name,
        practice_name=practice_name,
        appointment_date=appointment_date,
        appointment_time=appointment_time,
        provider_name=provider_name,
        practice_phone=practice_phone,
        **kwargs,
    )


def format_recall_prompt(
    template: str,
    patient_name: str,
    practice_name: str,
    practice_phone: str = "",
    vaccination_type: str = "",
    vaccination_name: str = "",
    **kwargs: Any,
) -> str:
    """Format a recall campaign prompt."""
    return template.format(
        time_greeting=get_time_greeting().lower(),
        patient_name=patient_name,
        practice_name=practice_name,
        practice_phone=practice_phone,
        vaccination_type=vaccination_type,
        vaccination_name=vaccination_name,
        **kwargs,
    )


def format_noshow_prompt(
    template: str,
    patient_name: str,
    practice_name: str,
    missed_date: str,
    practice_phone: str = "",
    **kwargs: Any,
) -> str:
    """Format a no-show follow-up prompt."""
    return template.format(
        time_greeting=get_time_greeting().lower(),
        patient_name=patient_name,
        practice_name=practice_name,
        missed_date=missed_date,
        practice_phone=practice_phone,
        **kwargs,
    )


def format_slot_options(slots: list[dict[str, str]], max_slots: int = 3) -> str:
    """Format time slot options for speech."""
    lines = []
    for i, slot in enumerate(slots[:max_slots]):
        lines.append(f"Option {i + 1}: {slot['description']}")
    return "\n".join(lines)


# ============ PROMPT BUILDER CLASS ============

class OutboundPromptBuilder:
    """Builder for constructing outbound call prompts."""

    def __init__(
        self,
        practice_name: str = "Ihre Arztpraxis",
        practice_phone: str = "",
    ):
        """Initialize prompt builder.

        Args:
            practice_name: Name of the medical practice
            practice_phone: Practice phone number
        """
        self.practice_name = practice_name
        self.practice_phone = practice_phone

    def build_reminder_introduction(self, patient_name: str) -> str:
        """Build appointment reminder introduction."""
        return format_reminder_prompt(
            REMINDER_INTRODUCTION,
            patient_name=patient_name,
            practice_name=self.practice_name,
            appointment_date="",
            appointment_time="",
            provider_name="",
        )

    def build_reminder_purpose(
        self,
        patient_name: str,
        appointment_date: str,
        appointment_time: str,
        provider_name: str,
    ) -> str:
        """Build appointment reminder purpose statement."""
        return format_reminder_prompt(
            REMINDER_PURPOSE,
            patient_name=patient_name,
            practice_name=self.practice_name,
            appointment_date=appointment_date,
            appointment_time=appointment_time,
            provider_name=provider_name,
        )

    def build_recall_introduction(self, patient_name: str) -> str:
        """Build recall campaign introduction."""
        return format_recall_prompt(
            RECALL_INTRODUCTION_GENERAL,
            patient_name=patient_name,
            practice_name=self.practice_name,
        )

    def build_recall_purpose(
        self,
        recall_type: str,
        vaccination_name: str = "",
    ) -> str:
        """Build recall campaign purpose statement based on type."""
        if recall_type == "preventive":
            return RECALL_PURPOSE_PREVENTIVE
        elif recall_type == "vaccination":
            if "grippe" in vaccination_name.lower() or "flu" in vaccination_name.lower():
                return RECALL_PURPOSE_VACCINATION_FLU
            elif "covid" in vaccination_name.lower():
                return RECALL_PURPOSE_VACCINATION_COVID
            else:
                return format_recall_prompt(
                    RECALL_PURPOSE_VACCINATION,
                    patient_name="",
                    practice_name=self.practice_name,
                    vaccination_type=vaccination_name,
                    vaccination_name=vaccination_name,
                )
        elif recall_type == "chronic":
            return RECALL_PURPOSE_DMP
        elif recall_type == "followup":
            return RECALL_PURPOSE_FOLLOWUP
        elif recall_type == "lab_results":
            return RECALL_PURPOSE_LAB_RESULTS
        else:
            return RECALL_PURPOSE_PREVENTIVE  # Default

    def build_noshow_introduction(self, patient_name: str) -> str:
        """Build no-show follow-up introduction."""
        return format_noshow_prompt(
            NOSHOW_INTRODUCTION,
            patient_name=patient_name,
            practice_name=self.practice_name,
            missed_date="",
        )

    def build_noshow_purpose(
        self,
        patient_name: str,
        missed_date: str,
    ) -> str:
        """Build no-show follow-up purpose statement."""
        return format_noshow_prompt(
            NOSHOW_PURPOSE,
            patient_name=patient_name,
            practice_name=self.practice_name,
            missed_date=missed_date,
        )

    def build_slot_offer(self, slots: list[dict[str, str]]) -> str:
        """Build slot offer message."""
        slot_options = format_slot_options(slots)
        return RECALL_SLOT_OFFER.format(slot_options=slot_options)

    def build_sms_confirmation(
        self,
        appointment_date: str,
        appointment_time: str,
        provider_name: str,
    ) -> str:
        """Build SMS confirmation message."""
        return REMINDER_SMS_CONFIRM.format(
            practice_name=self.practice_name,
            appointment_date=appointment_date,
            appointment_time=appointment_time,
            provider_name=provider_name,
            practice_phone=self.practice_phone,
        )

    def get_phrase(self, key: str) -> str:
        """Get a common phrase by key."""
        return PHRASES.get(key, "")
