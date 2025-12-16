"""Email classification prompts for German Handwerk.

LLM prompts optimized for classifying incoming emails from customers.
Extracts task_type, urgency, trade_category, and customer information.
"""

# Main email classification system prompt (German)
EMAIL_CLASSIFICATION_SYSTEM_PROMPT = """Du bist ein E-Mail-Klassifikator für deutsche Handwerksbetriebe.

Deine Aufgabe ist es, eingehende Kunden-E-Mails zu analysieren und folgende Informationen zu extrahieren:

## 1. Auftragstyp (task_type)
Wähle GENAU EINEN der folgenden Typen:

- **repairs**: Reparaturanfrage, Wartung, defektes Gerät, Störung, "funktioniert nicht"
- **quotes**: Anfrage für Angebot, Kostenvoranschlag, Preisanfrage, Neubau, Umbau
- **complaints**: Beschwerde, Reklamation, Unzufriedenheit, Problem mit vorheriger Arbeit
- **billing**: Frage zu Rechnung, Zahlung, Mahnung, Zahlungserinnerung
- **appointment**: Terminanfrage, Terminänderung, Terminverschiebung, Terminabsage
- **follow_up**: Nachfrage zu bestehendem Auftrag, Statusabfrage
- **general**: Allgemeine Anfrage, Information, sonstige Fragen
- **spam**: Werbung, Newsletter, irrelevante E-Mail

## 2. Dringlichkeit (urgency)
Wähle GENAU EINE der folgenden Stufen:

- **notfall**: SOFORT handeln erforderlich
  - Wasserrohrbruch, Überschwemmung
  - Heizungsausfall bei Kälte (<10°C)
  - Gasgeruch oder Gasleck
  - Stromausfall komplett
  - Sicherheitsrelevante Probleme

- **dringend**: Innerhalb von 24 Stunden
  - Teilfunktion ausgefallen ("Warmwasser geht nicht")
  - Elektrik teilweise defekt
  - Wichtiges Gerät kaputt
  - Blockierende Probleme ("kann nicht duschen")

- **normal**: Innerhalb dieser Woche
  - Standardreparatur
  - Terminanfragen
  - Normale Anfragen

- **routine**: Kein Zeitdruck
  - Langfristige Planungen
  - Wartungsanfragen
  - Allgemeine Informationen

## 3. Gewerkkategorie (trade_category)
Wähle GENAU EINE oder mehrere der folgenden Kategorien:

- **shk**: Sanitär, Heizung, Klima, Lüftung
  - Keywords: Heizung, Warmwasser, Therme, Kessel, Heizkörper, Rohre, Wasser, Bad, WC, Dusche, Sanitär, Klima, Lüftung

- **elektro**: Elektroinstallation, Elektrik
  - Keywords: Strom, Elektrik, Sicherung, FI-Schalter, Steckdose, Licht, Lampe, Kabel, Schalter

- **sanitaer**: Spezifisch Bad und Wasserleitungen
  - Keywords: Bad, WC, Toilette, Waschbecken, Dusche, Badewanne, Armatur, Wasserhahn

- **dachdecker**: Dacharbeiten
  - Keywords: Dach, Ziegel, Dachrinne, Dachfenster, Abdichtung, Isolierung

- **schlosser**: Schlosserei, Metallbau
  - Keywords: Tür, Schloss, Schlüssel, Fenster, Gitter, Metall

- **maler**: Malerarbeiten
  - Keywords: Streichen, Farbe, Tapete, Wand, Fassade, Lackieren

- **tischler**: Tischlerarbeiten, Möbel
  - Keywords: Möbel, Holz, Schrank, Tür, Fenster, Parkett, Laminat

- **allgemein**: Unklar oder mehrere Gewerke

## 4. Kundeninformationen extrahieren
Extrahiere folgende Daten, falls in der E-Mail genannt:

- **name**: Kundenname (Vor- und/oder Nachname)
- **phone**: Telefonnummer (alle deutschen Formate erkennen: +49, 0xxx, mit/ohne Bindestriche)
- **street**: Straße mit Hausnummer
- **plz**: Postleitzahl (5 Ziffern)
- **city**: Stadt/Ort
- **preferred_time**: Bevorzugte Terminzeit, falls genannt

## Antwortformat

Du MUSST in folgendem JSON-Format antworten (keine anderen Texte!):

```json
{
    "task_type": "repairs|quotes|complaints|billing|appointment|follow_up|general|spam",
    "urgency": "notfall|dringend|normal|routine",
    "trade_category": "shk|elektro|sanitaer|dachdecker|schlosser|maler|tischler|allgemein",
    "customer_info": {
        "name": "Max Müller" oder null,
        "phone": "+49176123456" oder null,
        "street": "Musterstraße 123" oder null,
        "plz": "72379" oder null,
        "city": "Hechingen" oder null,
        "preferred_time": "vormittags" oder null
    },
    "summary": "Kurze Zusammenfassung in 1-2 Sätzen auf Deutsch",
    "keywords": ["keyword1", "keyword2"],
    "confidence": 0.0-1.0,
    "needs_human_review": true/false,
    "suggested_response": "Kurze Antwort-Empfehlung falls sinnvoll" oder null
}
```

## Wichtige Regeln

1. Bei Notfällen (Gasgeruch, Wasserrohrbruch, etc.) IMMER urgency="notfall" setzen
2. Bei Beschwerden über vorherige Arbeit: task_type="complaints", auch wenn Reparatur nötig
3. Bei Spam oder Werbung: task_type="spam", urgency="routine"
4. Bei unklarer Dringlichkeit: urgency="normal" (Standardwert)
5. confidence < 0.7: needs_human_review=true setzen
6. Alle Felder müssen gefüllt sein (ggf. mit null für unbekannt)"""


# User prompt template for email classification
EMAIL_CLASSIFICATION_USER_PROMPT = """Analysiere diese E-Mail und extrahiere die Informationen gemäß den Anweisungen.

**Betreff:** {subject}

**Absender:** {sender}

**E-Mail-Text:**
{body}

---

Antworte NUR mit dem JSON-Objekt, keine anderen Texte."""


# Auto-reply templates (German)
EMAIL_AUTO_REPLY_TEMPLATES = {
    "notfall": """Sehr geehrte/r {customer_name},

vielen Dank für Ihre Nachricht.

⚠️ Wir haben Ihre Anfrage als DRINGLICH eingestuft und werden uns schnellstmöglich bei Ihnen melden.

Bei einem akuten Notfall (Gasgeruch, Wasserrohrbruch) rufen Sie bitte sofort unsere Notfall-Hotline an: {emergency_phone}

Ihre Auftragsnummer: {ticket_number}

Mit freundlichen Grüßen
{company_name}""",

    "dringend": """Sehr geehrte/r {customer_name},

vielen Dank für Ihre Nachricht.

Wir haben Ihre Anfrage erhalten und werden uns innerhalb der nächsten 24 Stunden bei Ihnen melden.

Ihre Auftragsnummer: {ticket_number}

Mit freundlichen Grüßen
{company_name}""",

    "normal": """Sehr geehrte/r {customer_name},

vielen Dank für Ihre Anfrage.

Wir werden uns zeitnah bei Ihnen melden, um Ihr Anliegen zu besprechen.

Ihre Auftragsnummer: {ticket_number}

Mit freundlichen Grüßen
{company_name}""",

    "routine": """Sehr geehrte/r {customer_name},

vielen Dank für Ihre Anfrage.

Wir haben Ihre Nachricht erhalten und werden uns innerhalb der nächsten Werktage bei Ihnen melden.

Ihre Auftragsnummer: {ticket_number}

Mit freundlichen Grüßen
{company_name}""",

    "spam": None,  # No auto-reply for spam
}


# Task type descriptions (for routing display)
TASK_TYPE_LABELS = {
    "repairs": "Reparaturanfrage",
    "quotes": "Angebotsanfrage",
    "complaints": "Reklamation",
    "billing": "Rechnungsanfrage",
    "appointment": "Terminanfrage",
    "follow_up": "Nachfrage",
    "general": "Allgemeine Anfrage",
    "spam": "Spam/Werbung",
}

# Urgency labels
URGENCY_LABELS = {
    "notfall": "🔴 Notfall",
    "dringend": "🟠 Dringend",
    "normal": "🟡 Normal",
    "routine": "🟢 Routine",
}

# Trade category labels
TRADE_CATEGORY_LABELS = {
    "shk": "Sanitär/Heizung/Klima",
    "elektro": "Elektro",
    "sanitaer": "Sanitär",
    "dachdecker": "Dachdecker",
    "schlosser": "Schlosser",
    "maler": "Maler",
    "tischler": "Tischler",
    "allgemein": "Allgemein",
}
