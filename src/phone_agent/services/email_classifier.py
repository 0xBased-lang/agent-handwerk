"""Email Classifier service.

Uses LLM (Groq) to classify incoming emails for German Handwerk companies.
Extracts task_type, urgency, trade_category, and customer information.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

from itf_shared import get_logger

from phone_agent.services.email_parser import ParsedEmail
from phone_agent.industry.handwerk.email_prompts import (
    EMAIL_CLASSIFICATION_SYSTEM_PROMPT,
    EMAIL_CLASSIFICATION_USER_PROMPT,
)

log = get_logger(__name__)


@dataclass
class EmailClassification:
    """Result of email classification."""

    # Classification
    task_type: str  # repairs, quotes, complaints, billing, appointment, follow_up, general, spam
    urgency: str  # notfall, dringend, normal, routine
    trade_category: str  # shk, elektro, sanitaer, etc.

    # Customer info extracted
    customer_name: str | None = None
    customer_phone: str | None = None
    customer_street: str | None = None
    customer_plz: str | None = None
    customer_city: str | None = None
    preferred_time: str | None = None

    # Analysis
    summary: str = ""
    keywords: list[str] = field(default_factory=list)
    confidence: float = 0.0
    needs_human_review: bool = False
    suggested_response: str | None = None

    # Raw LLM response
    raw_response: dict[str, Any] = field(default_factory=dict)


class EmailClassifier:
    """Classify emails using LLM.

    Uses Groq API for fast inference with Llama 3.3 70B.
    Falls back to pattern matching if LLM unavailable.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "llama-3.3-70b-versatile",
        temperature: float = 0.3,  # Low temperature for consistent classification
        max_tokens: int = 1024,
    ):
        """Initialize email classifier.

        Args:
            api_key: Groq API key (or from GROQ_API_KEY env)
            model: Model to use for classification
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
        """
        self.api_key = api_key or os.environ.get("GROQ_API_KEY", "")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._llm = None

    def _get_llm(self):
        """Lazily initialize LLM client."""
        if self._llm is None and self.api_key:
            try:
                from phone_agent.ai.cloud.groq_client import GroqLanguageModel

                self._llm = GroqLanguageModel(
                    api_key=self.api_key,
                    model=self.model,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                )
                self._llm.load()
                log.info("Email classifier LLM initialized", model=self.model)
            except Exception as e:
                log.error("Failed to initialize LLM for email classification", error=str(e))
                self._llm = None
        return self._llm

    async def classify(self, email: ParsedEmail) -> EmailClassification:
        """Classify an email using LLM.

        Args:
            email: Parsed email to classify

        Returns:
            EmailClassification with extracted information
        """
        # Try LLM classification first
        llm = self._get_llm()

        if llm:
            try:
                return await self._classify_with_llm(email)
            except Exception as e:
                log.error("LLM classification failed, using fallback", error=str(e))

        # Fallback to pattern matching
        return self._classify_with_patterns(email)

    async def _classify_with_llm(self, email: ParsedEmail) -> EmailClassification:
        """Classify email using LLM."""
        # Build the user prompt
        user_prompt = EMAIL_CLASSIFICATION_USER_PROMPT.format(
            subject=email.subject or "(kein Betreff)",
            sender=f"{email.sender_name or ''} <{email.sender_email}>".strip(),
            body=email.plain_text[:3000],  # Limit body length
        )

        log.debug(
            "Classifying email with LLM",
            subject=email.subject[:50] if email.subject else None,
            body_length=len(email.plain_text),
        )

        # Call LLM
        response = await self._llm.generate_async(
            prompt=user_prompt,
            system_prompt=EMAIL_CLASSIFICATION_SYSTEM_PROMPT,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

        # Parse JSON response
        classification = self._parse_llm_response(response, email)

        log.info(
            "Email classified",
            task_type=classification.task_type,
            urgency=classification.urgency,
            trade_category=classification.trade_category,
            confidence=classification.confidence,
        )

        return classification

    def _parse_llm_response(self, response: str, email: ParsedEmail) -> EmailClassification:
        """Parse LLM JSON response into EmailClassification."""
        # Extract JSON from response (handle markdown code blocks)
        json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to find raw JSON
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            json_str = json_match.group(0) if json_match else response

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            log.warning("Failed to parse LLM JSON response", error=str(e), response=response[:200])
            return self._classify_with_patterns(email)

        # Extract customer info
        customer_info = data.get("customer_info", {}) or {}

        return EmailClassification(
            task_type=data.get("task_type", "general"),
            urgency=data.get("urgency", "normal"),
            trade_category=data.get("trade_category", "allgemein"),
            customer_name=customer_info.get("name") or email.sender_name,
            customer_phone=customer_info.get("phone"),
            customer_street=customer_info.get("street"),
            customer_plz=customer_info.get("plz"),
            customer_city=customer_info.get("city"),
            preferred_time=customer_info.get("preferred_time"),
            summary=data.get("summary", ""),
            keywords=data.get("keywords", []),
            confidence=float(data.get("confidence", 0.7)),
            needs_human_review=data.get("needs_human_review", False),
            suggested_response=data.get("suggested_response"),
            raw_response=data,
        )

    def _classify_with_patterns(self, email: ParsedEmail) -> EmailClassification:
        """Fallback classification using pattern matching.

        Used when LLM is unavailable.
        """
        text = f"{email.subject or ''} {email.plain_text}".lower()

        # Detect task type
        task_type = self._detect_task_type(text)

        # Detect urgency
        urgency = self._detect_urgency(text)

        # Detect trade category
        trade_category = self._detect_trade_category(text)

        # Extract customer info from parsed email
        customer_info = email_parser.EmailParser().extract_customer_info(email) if email.plain_text else {}

        return EmailClassification(
            task_type=task_type,
            urgency=urgency,
            trade_category=trade_category,
            customer_name=customer_info.get("name") or email.sender_name,
            customer_phone=customer_info.get("phone"),
            customer_street=customer_info.get("address"),
            customer_plz=customer_info.get("plz"),
            customer_city=customer_info.get("city"),
            summary=f"Automatisch klassifiziert: {email.subject or 'Keine Betreffzeile'}",
            confidence=0.5,  # Lower confidence for pattern matching
            needs_human_review=True,
        )

    def _detect_task_type(self, text: str) -> str:
        """Detect task type from text patterns."""
        # Priority order matters
        patterns = {
            "complaints": [
                "beschwerde", "reklamation", "unzufrieden", "schlecht",
                "nicht zufrieden", "enttäuscht", "mangel", "pfusch",
            ],
            "repairs": [
                "reparatur", "kaputt", "defekt", "funktioniert nicht",
                "geht nicht", "ausgefallen", "störung", "leck", "tropft",
                "undicht", "verstopft", "kein wasser", "keine heizung",
            ],
            "quotes": [
                "angebot", "kostenvoranschlag", "preis", "kosten",
                "was kostet", "wie teuer", "neubau", "umbau", "installation",
            ],
            "billing": [
                "rechnung", "zahlung", "mahnung", "bezahlen", "überweisung",
                "bankverbindung", "kontonummer",
            ],
            "appointment": [
                "termin", "zeit", "wann", "verfügbar", "können sie kommen",
                "verschieben", "absagen", "neuen termin",
            ],
            "follow_up": [
                "nachfrage", "status", "wie weit", "stand der dinge",
                "wann fertig", "fortschritt",
            ],
            "spam": [
                "newsletter", "abbestellen", "werbung", "anzeige",
                "sonderangebot", "rabatt", "gewonnen",
            ],
        }

        for task_type, keywords in patterns.items():
            if any(keyword in text for keyword in keywords):
                return task_type

        return "general"

    def _detect_urgency(self, text: str) -> str:
        """Detect urgency from text patterns."""
        # Emergency patterns
        notfall_patterns = [
            "notfall", "notdienst", "sofort", "dringend sehr",
            "wasserrohrbruch", "rohrbruch", "überschwemmung", "überflutung",
            "gasgeruch", "gas riecht", "gasleck", "gasaustritt",
            "stromausfall", "kein strom", "brand", "feuer",
            "heizung aus", "keine heizung", "heizung defekt",
        ]

        if any(pattern in text for pattern in notfall_patterns):
            return "notfall"

        # Urgent patterns
        dringend_patterns = [
            "dringend", "schnell", "heute noch", "so schnell wie möglich",
            "bald", "wichtig", "eilig", "asap", "umgehend",
            "warmwasser geht nicht", "kein warmwasser",
            "dusche geht nicht", "wc verstopft",
        ]

        if any(pattern in text for pattern in dringend_patterns):
            return "dringend"

        # Routine patterns
        routine_patterns = [
            "keine eile", "irgendwann", "wenn zeit ist", "nächsten monat",
            "nächstes jahr", "langfristig", "wartung",
        ]

        if any(pattern in text for pattern in routine_patterns):
            return "routine"

        return "normal"

    def _detect_trade_category(self, text: str) -> str:
        """Detect trade category from text patterns."""
        patterns = {
            "shk": [
                "heizung", "warmwasser", "therme", "kessel", "heizkörper",
                "lüftung", "klima", "klimaanlage", "wärmepumpe",
            ],
            "elektro": [
                "strom", "elektr", "sicherung", "fi-schalter", "steckdose",
                "licht", "lampe", "kabel", "schalter", "elektrik",
            ],
            "sanitaer": [
                "bad", "wc", "toilette", "waschbecken", "dusche", "badewanne",
                "armatur", "wasserhahn", "rohre", "abfluss", "verstopft",
            ],
            "dachdecker": [
                "dach", "ziegel", "dachrinne", "dachfenster", "abdichtung",
            ],
            "schlosser": [
                "tür", "schloss", "schlüssel", "fenster", "gitter",
            ],
            "maler": [
                "streichen", "farbe", "tapete", "wand", "fassade", "lackieren",
            ],
            "tischler": [
                "möbel", "holz", "schrank", "parkett", "laminat",
            ],
        }

        # Count matches for each category
        scores = {}
        for category, keywords in patterns.items():
            score = sum(1 for keyword in keywords if keyword in text)
            if score > 0:
                scores[category] = score

        if scores:
            return max(scores, key=scores.get)

        return "allgemein"


# Import for fallback pattern matching
from phone_agent.services import email_parser
