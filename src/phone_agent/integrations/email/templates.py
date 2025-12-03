"""Email Templates for German Locale.

Provides pre-built email templates for common use cases:
- Appointment confirmation
- Appointment reminder
- Appointment cancellation
- Appointment rescheduling
- Welcome/registration
- General notifications

All templates are available in both plain text and HTML formats.
Templates use German language with professional medical practice tone.

Security: All user-controlled fields are HTML-escaped to prevent XSS attacks.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date, time
from html import escape as html_escape
from typing import Any

from phone_agent.integrations.email.base import EmailMessage, EmailPriority


def _escape(value: str) -> str:
    """Escape HTML special characters to prevent XSS.

    Args:
        value: String that may contain user input

    Returns:
        HTML-escaped string safe for embedding in HTML
    """
    return html_escape(value, quote=True)


@dataclass
class TemplateContext:
    """Common context for email templates."""

    practice_name: str
    practice_address: str = ""
    practice_phone: str = ""
    practice_email: str = ""
    practice_website: str = ""
    logo_url: str = ""


def _base_html_template(content: str, ctx: TemplateContext) -> str:
    """Wrap content in base HTML email template.

    Args:
        content: Main email content (should already be escaped)
        ctx: Practice context

    Returns:
        Complete HTML email
    """
    # Escape all user-controlled context fields
    practice_name = _escape(ctx.practice_name)
    practice_address = _escape(ctx.practice_address) if ctx.practice_address else ""
    practice_phone = _escape(ctx.practice_phone) if ctx.practice_phone else ""
    practice_email = _escape(ctx.practice_email) if ctx.practice_email else ""
    practice_website = _escape(ctx.practice_website) if ctx.practice_website else ""

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{practice_name}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #333333;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            background-color: #ffffff;
            border-radius: 8px;
            padding: 30px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .header {{
            text-align: center;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 2px solid #e0e0e0;
        }}
        .header h1 {{
            color: #2c5aa0;
            margin: 0;
            font-size: 24px;
        }}
        .content {{
            margin-bottom: 30px;
        }}
        .appointment-box {{
            background-color: #f8f9fa;
            border-left: 4px solid #2c5aa0;
            padding: 15px 20px;
            margin: 20px 0;
            border-radius: 0 4px 4px 0;
        }}
        .appointment-box strong {{
            color: #2c5aa0;
        }}
        .button {{
            display: inline-block;
            background-color: #2c5aa0;
            color: #ffffff;
            padding: 12px 24px;
            text-decoration: none;
            border-radius: 4px;
            margin: 10px 5px;
        }}
        .button-secondary {{
            background-color: #6c757d;
        }}
        .footer {{
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #e0e0e0;
            font-size: 12px;
            color: #666666;
            text-align: center;
        }}
        .important {{
            color: #dc3545;
            font-weight: bold;
        }}
        @media only screen and (max-width: 480px) {{
            body {{
                padding: 10px;
            }}
            .container {{
                padding: 20px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{practice_name}</h1>
        </div>
        <div class="content">
            {content}
        </div>
        <div class="footer">
            <p><strong>{practice_name}</strong></p>
            {f'<p>{practice_address}</p>' if practice_address else ''}
            {f'<p>Tel: {practice_phone}</p>' if practice_phone else ''}
            {f'<p>E-Mail: {practice_email}</p>' if practice_email else ''}
            {f'<p><a href="{practice_website}">{practice_website}</a></p>' if practice_website else ''}
            <p style="margin-top: 15px; font-size: 11px; color: #999;">
                Diese E-Mail wurde automatisch generiert. Bitte antworten Sie nicht direkt auf diese E-Mail.
            </p>
        </div>
    </div>
</body>
</html>"""


def _format_date_german(d: date) -> str:
    """Format date in German format.

    Args:
        d: Date to format

    Returns:
        Date string like "Montag, 15. Januar 2024"
    """
    weekdays = [
        "Montag",
        "Dienstag",
        "Mittwoch",
        "Donnerstag",
        "Freitag",
        "Samstag",
        "Sonntag",
    ]
    months = [
        "Januar",
        "Februar",
        "März",
        "April",
        "Mai",
        "Juni",
        "Juli",
        "August",
        "September",
        "Oktober",
        "November",
        "Dezember",
    ]

    weekday = weekdays[d.weekday()]
    month = months[d.month - 1]
    return f"{weekday}, {d.day}. {month} {d.year}"


def _format_time_german(t: time) -> str:
    """Format time in German format.

    Args:
        t: Time to format

    Returns:
        Time string like "10:30 Uhr"
    """
    return f"{t.hour:02d}:{t.minute:02d} Uhr"


# =============================================================================
# Appointment Confirmation Template
# =============================================================================


def appointment_confirmation_text(
    patient_name: str,
    appointment_date: date,
    appointment_time: time,
    provider_name: str,
    appointment_type: str,
    ctx: TemplateContext,
    notes: str = "",
) -> str:
    """Generate appointment confirmation plain text.

    Args:
        patient_name: Patient full name
        appointment_date: Appointment date
        appointment_time: Appointment time
        provider_name: Doctor/provider name
        appointment_type: Type of appointment
        ctx: Practice context
        notes: Additional notes

    Returns:
        Plain text email body
    """
    date_str = _format_date_german(appointment_date)
    time_str = _format_time_german(appointment_time)

    text = f"""Guten Tag {patient_name},

Ihr Termin wurde erfolgreich gebucht.

TERMINDETAILS
=============
Datum: {date_str}
Uhrzeit: {time_str}
Bei: {provider_name}
Art: {appointment_type}
Praxis: {ctx.practice_name}
{f'Adresse: {ctx.practice_address}' if ctx.practice_address else ''}

{f'Hinweis: {notes}' if notes else ''}

WICHTIGE INFORMATIONEN
======================
- Bitte erscheinen Sie 10 Minuten vor Ihrem Termin
- Bringen Sie Ihre Versicherungskarte und ggf. Befunde mit
- Bei Verhinderung bitten wir um rechtzeitige Absage (mind. 24 Stunden vorher)

TERMIN ABSAGEN ODER VERSCHIEBEN
===============================
{f'Telefon: {ctx.practice_phone}' if ctx.practice_phone else ''}
{f'E-Mail: {ctx.practice_email}' if ctx.practice_email else ''}

Wir freuen uns auf Ihren Besuch!

Mit freundlichen Grüßen
Ihr Team der {ctx.practice_name}

---
Diese E-Mail wurde automatisch generiert.
"""
    return text


def appointment_confirmation_html(
    patient_name: str,
    appointment_date: date,
    appointment_time: time,
    provider_name: str,
    appointment_type: str,
    ctx: TemplateContext,
    notes: str = "",
) -> str:
    """Generate appointment confirmation HTML.

    Args:
        patient_name: Patient full name
        appointment_date: Appointment date
        appointment_time: Appointment time
        provider_name: Doctor/provider name
        appointment_type: Type of appointment
        ctx: Practice context
        notes: Additional notes

    Returns:
        HTML email body
    """
    date_str = _format_date_german(appointment_date)
    time_str = _format_time_german(appointment_time)

    # Escape user-controlled fields
    patient_name_safe = _escape(patient_name)
    provider_name_safe = _escape(provider_name)
    appointment_type_safe = _escape(appointment_type)
    notes_safe = _escape(notes) if notes else ""
    practice_name_safe = _escape(ctx.practice_name)

    content = f"""
        <p>Guten Tag {patient_name_safe},</p>
        <p>Ihr Termin wurde erfolgreich gebucht.</p>

        <div class="appointment-box">
            <p><strong>Datum:</strong> {date_str}</p>
            <p><strong>Uhrzeit:</strong> {time_str}</p>
            <p><strong>Bei:</strong> {provider_name_safe}</p>
            <p><strong>Art:</strong> {appointment_type_safe}</p>
        </div>

        {f'<p><em>Hinweis: {notes_safe}</em></p>' if notes_safe else ''}

        <h3>Wichtige Informationen</h3>
        <ul>
            <li>Bitte erscheinen Sie 10 Minuten vor Ihrem Termin</li>
            <li>Bringen Sie Ihre Versicherungskarte und ggf. Befunde mit</li>
            <li>Bei Verhinderung bitten wir um rechtzeitige Absage (mind. 24 Stunden vorher)</li>
        </ul>

        <p>Wir freuen uns auf Ihren Besuch!</p>

        <p>Mit freundlichen Grüßen<br>
        Ihr Team der {practice_name_safe}</p>
    """

    return _base_html_template(content, ctx)


def create_appointment_confirmation_email(
    to_email: str,
    patient_name: str,
    appointment_date: date,
    appointment_time: time,
    provider_name: str,
    appointment_type: str,
    ctx: TemplateContext,
    notes: str = "",
    reference: str | None = None,
) -> EmailMessage:
    """Create appointment confirmation email message.

    Args:
        to_email: Recipient email
        patient_name: Patient full name
        appointment_date: Appointment date
        appointment_time: Appointment time
        provider_name: Doctor/provider name
        appointment_type: Type of appointment
        ctx: Practice context
        notes: Additional notes
        reference: External reference ID

    Returns:
        EmailMessage ready to send
    """
    date_str = appointment_date.strftime("%d.%m.%Y")

    return EmailMessage(
        to=to_email,
        subject=f"Terminbestätigung - {ctx.practice_name} am {date_str}",
        body_text=appointment_confirmation_text(
            patient_name,
            appointment_date,
            appointment_time,
            provider_name,
            appointment_type,
            ctx,
            notes,
        ),
        body_html=appointment_confirmation_html(
            patient_name,
            appointment_date,
            appointment_time,
            provider_name,
            appointment_type,
            ctx,
            notes,
        ),
        reference=reference,
        tags=["appointment", "confirmation"],
    )


# =============================================================================
# Appointment Reminder Template
# =============================================================================


def appointment_reminder_text(
    patient_name: str,
    appointment_date: date,
    appointment_time: time,
    provider_name: str,
    ctx: TemplateContext,
    hours_before: int = 24,
) -> str:
    """Generate appointment reminder plain text."""
    date_str = _format_date_german(appointment_date)
    time_str = _format_time_german(appointment_time)

    if hours_before <= 24:
        time_text = "morgen"
    else:
        time_text = f"am {date_str}"

    text = f"""Guten Tag {patient_name},

Wir möchten Sie an Ihren bevorstehenden Termin erinnern.

TERMINDETAILS
=============
Datum: {date_str} ({time_text})
Uhrzeit: {time_str}
Bei: {provider_name}
Praxis: {ctx.practice_name}
{f'Adresse: {ctx.practice_address}' if ctx.practice_address else ''}

BITTE BEACHTEN
==============
- Erscheinen Sie 10 Minuten vor Ihrem Termin
- Bringen Sie Ihre Versicherungskarte mit
- Tragen Sie bei Erkältungssymptomen bitte eine Maske

TERMIN ABSAGEN
==============
Falls Sie den Termin nicht wahrnehmen können, bitten wir um rechtzeitige Absage:
{f'Telefon: {ctx.practice_phone}' if ctx.practice_phone else ''}

Wir freuen uns auf Sie!

Mit freundlichen Grüßen
Ihr Team der {ctx.practice_name}
"""
    return text


def appointment_reminder_html(
    patient_name: str,
    appointment_date: date,
    appointment_time: time,
    provider_name: str,
    ctx: TemplateContext,
    hours_before: int = 24,
) -> str:
    """Generate appointment reminder HTML."""
    date_str = _format_date_german(appointment_date)
    time_str = _format_time_german(appointment_time)

    if hours_before <= 24:
        time_text = "morgen"
    else:
        time_text = f"am {date_str}"

    # Escape user-controlled fields
    patient_name_safe = _escape(patient_name)
    provider_name_safe = _escape(provider_name)
    practice_name_safe = _escape(ctx.practice_name)

    content = f"""
        <p>Guten Tag {patient_name_safe},</p>
        <p>Wir möchten Sie an Ihren bevorstehenden Termin <strong>{time_text}</strong> erinnern.</p>

        <div class="appointment-box">
            <p><strong>Datum:</strong> {date_str}</p>
            <p><strong>Uhrzeit:</strong> {time_str}</p>
            <p><strong>Bei:</strong> {provider_name_safe}</p>
        </div>

        <h3>Bitte beachten</h3>
        <ul>
            <li>Erscheinen Sie 10 Minuten vor Ihrem Termin</li>
            <li>Bringen Sie Ihre Versicherungskarte mit</li>
            <li>Tragen Sie bei Erkältungssymptomen bitte eine Maske</li>
        </ul>

        <p>Falls Sie den Termin nicht wahrnehmen können, bitten wir um rechtzeitige Absage.</p>

        <p>Wir freuen uns auf Sie!</p>

        <p>Mit freundlichen Grüßen<br>
        Ihr Team der {practice_name_safe}</p>
    """

    return _base_html_template(content, ctx)


def create_appointment_reminder_email(
    to_email: str,
    patient_name: str,
    appointment_date: date,
    appointment_time: time,
    provider_name: str,
    ctx: TemplateContext,
    hours_before: int = 24,
    reference: str | None = None,
) -> EmailMessage:
    """Create appointment reminder email message."""
    date_str = appointment_date.strftime("%d.%m.%Y")

    return EmailMessage(
        to=to_email,
        subject=f"Terminerinnerung - {ctx.practice_name} am {date_str}",
        body_text=appointment_reminder_text(
            patient_name,
            appointment_date,
            appointment_time,
            provider_name,
            ctx,
            hours_before,
        ),
        body_html=appointment_reminder_html(
            patient_name,
            appointment_date,
            appointment_time,
            provider_name,
            ctx,
            hours_before,
        ),
        reference=reference,
        tags=["appointment", "reminder"],
        priority=EmailPriority.HIGH,
    )


# =============================================================================
# Appointment Cancellation Template
# =============================================================================


def appointment_cancellation_text(
    patient_name: str,
    appointment_date: date,
    appointment_time: time,
    ctx: TemplateContext,
    reason: str = "",
) -> str:
    """Generate appointment cancellation plain text."""
    date_str = _format_date_german(appointment_date)
    time_str = _format_time_german(appointment_time)

    text = f"""Guten Tag {patient_name},

Hiermit bestätigen wir die Stornierung Ihres Termins.

STORNIERTER TERMIN
==================
Datum: {date_str}
Uhrzeit: {time_str}
{f'Grund: {reason}' if reason else ''}

NEUEN TERMIN VEREINBAREN
========================
Um einen neuen Termin zu vereinbaren, kontaktieren Sie uns bitte:
{f'Telefon: {ctx.practice_phone}' if ctx.practice_phone else ''}
{f'E-Mail: {ctx.practice_email}' if ctx.practice_email else ''}

Mit freundlichen Grüßen
Ihr Team der {ctx.practice_name}
"""
    return text


def appointment_cancellation_html(
    patient_name: str,
    appointment_date: date,
    appointment_time: time,
    ctx: TemplateContext,
    reason: str = "",
) -> str:
    """Generate appointment cancellation HTML."""
    date_str = _format_date_german(appointment_date)
    time_str = _format_time_german(appointment_time)

    # Escape user-controlled fields
    patient_name_safe = _escape(patient_name)
    reason_safe = _escape(reason) if reason else ""
    practice_name_safe = _escape(ctx.practice_name)
    practice_phone_safe = _escape(ctx.practice_phone) if ctx.practice_phone else ""
    practice_email_safe = _escape(ctx.practice_email) if ctx.practice_email else ""

    content = f"""
        <p>Guten Tag {patient_name_safe},</p>
        <p>Hiermit bestätigen wir die Stornierung Ihres Termins.</p>

        <div class="appointment-box" style="border-left-color: #dc3545;">
            <p><strong>Stornierter Termin</strong></p>
            <p>Datum: {date_str}</p>
            <p>Uhrzeit: {time_str}</p>
            {f'<p>Grund: {reason_safe}</p>' if reason_safe else ''}
        </div>

        <h3>Neuen Termin vereinbaren</h3>
        <p>Um einen neuen Termin zu vereinbaren, kontaktieren Sie uns bitte:</p>
        <ul>
            {f'<li>Telefon: {practice_phone_safe}</li>' if practice_phone_safe else ''}
            {f'<li>E-Mail: {practice_email_safe}</li>' if practice_email_safe else ''}
        </ul>

        <p>Mit freundlichen Grüßen<br>
        Ihr Team der {practice_name_safe}</p>
    """

    return _base_html_template(content, ctx)


def create_appointment_cancellation_email(
    to_email: str,
    patient_name: str,
    appointment_date: date,
    appointment_time: time,
    ctx: TemplateContext,
    reason: str = "",
    reference: str | None = None,
) -> EmailMessage:
    """Create appointment cancellation email message."""
    date_str = appointment_date.strftime("%d.%m.%Y")

    return EmailMessage(
        to=to_email,
        subject=f"Terminabsage - {ctx.practice_name} am {date_str}",
        body_text=appointment_cancellation_text(
            patient_name,
            appointment_date,
            appointment_time,
            ctx,
            reason,
        ),
        body_html=appointment_cancellation_html(
            patient_name,
            appointment_date,
            appointment_time,
            ctx,
            reason,
        ),
        reference=reference,
        tags=["appointment", "cancellation"],
    )


# =============================================================================
# Appointment Rescheduling Template
# =============================================================================


def create_appointment_rescheduled_email(
    to_email: str,
    patient_name: str,
    old_date: date,
    old_time: time,
    new_date: date,
    new_time: time,
    provider_name: str,
    ctx: TemplateContext,
    reference: str | None = None,
) -> EmailMessage:
    """Create appointment rescheduled email message."""
    old_date_str = _format_date_german(old_date)
    old_time_str = _format_time_german(old_time)
    new_date_str = _format_date_german(new_date)
    new_time_str = _format_time_german(new_time)

    # Plain text doesn't need escaping
    body_text = f"""Guten Tag {patient_name},

Ihr Termin wurde erfolgreich umgebucht.

ALTER TERMIN (STORNIERT)
========================
Datum: {old_date_str}
Uhrzeit: {old_time_str}

NEUER TERMIN
============
Datum: {new_date_str}
Uhrzeit: {new_time_str}
Bei: {provider_name}
Praxis: {ctx.practice_name}
{f'Adresse: {ctx.practice_address}' if ctx.practice_address else ''}

Wir freuen uns auf Ihren Besuch!

Mit freundlichen Grüßen
Ihr Team der {ctx.practice_name}
"""

    # Escape user-controlled fields for HTML
    patient_name_safe = _escape(patient_name)
    provider_name_safe = _escape(provider_name)
    practice_name_safe = _escape(ctx.practice_name)

    content = f"""
        <p>Guten Tag {patient_name_safe},</p>
        <p>Ihr Termin wurde erfolgreich umgebucht.</p>

        <div class="appointment-box" style="border-left-color: #dc3545; opacity: 0.7;">
            <p><strong>Alter Termin (storniert)</strong></p>
            <p>Datum: {old_date_str}</p>
            <p>Uhrzeit: {old_time_str}</p>
        </div>

        <div class="appointment-box">
            <p><strong>Neuer Termin</strong></p>
            <p>Datum: {new_date_str}</p>
            <p>Uhrzeit: {new_time_str}</p>
            <p>Bei: {provider_name_safe}</p>
        </div>

        <p>Wir freuen uns auf Ihren Besuch!</p>

        <p>Mit freundlichen Grüßen<br>
        Ihr Team der {practice_name_safe}</p>
    """

    body_html = _base_html_template(content, ctx)
    new_date_short = new_date.strftime("%d.%m.%Y")

    return EmailMessage(
        to=to_email,
        subject=f"Terminumbuchung - {practice_name_safe} am {new_date_short}",
        body_text=body_text,
        body_html=body_html,
        reference=reference,
        tags=["appointment", "reschedule"],
    )
