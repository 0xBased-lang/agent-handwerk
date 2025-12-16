"""Tests for Email Agent services.

Tests email parsing, classification, and IMAP polling functionality.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from phone_agent.services.email_parser import EmailParser, ParsedEmail, EmailAttachment
from phone_agent.services.email_classifier import EmailClassifier, EmailClassification
from phone_agent.services.email_poller import EmailConfig, EmailEncryption


# ============================================================================
# Email Parser Tests
# ============================================================================


class TestEmailParser:
    """Tests for EmailParser service."""

    @pytest.fixture
    def parser(self):
        """Create email parser instance."""
        return EmailParser()

    def test_parse_simple_email(self, parser):
        """Test parsing a simple text email."""
        raw_email = """From: max.mueller@example.de
To: info@handwerk.de
Subject: Heizung defekt
Date: Mon, 16 Dec 2024 10:30:00 +0100
Content-Type: text/plain; charset=utf-8

Guten Tag,

unsere Heizung funktioniert nicht mehr.
Bitte rufen Sie uns an: 0711-12345678

Mit freundlichen Gruessen
Max Mueller
72379 Hechingen""".encode("utf-8")

        result = parser.parse(raw_email)

        assert result.subject == "Heizung defekt"
        assert result.sender_email == "max.mueller@example.de"
        assert "Heizung funktioniert nicht" in result.plain_text
        assert result.recipient_email == "info@handwerk.de"

    def test_parse_html_email(self, parser):
        """Test parsing HTML email with text extraction."""
        raw_email = """From: kunde@example.de
To: service@firma.de
Subject: Angebot erforderlich
Content-Type: text/html; charset=utf-8

<html>
<body>
<p>Sehr geehrte Damen und Herren,</p>
<p>ich benoetige ein <strong>Angebot</strong> fuer eine neue Heizungsanlage.</p>
<p>Mit freundlichen Gruessen</p>
</body>
</html>""".encode("utf-8")

        result = parser.parse(raw_email)

        assert result.subject == "Angebot erforderlich"
        assert "Angebot" in result.plain_text
        assert "Heizungsanlage" in result.plain_text

    def test_parse_multipart_email(self, parser):
        """Test parsing multipart email with text and HTML parts."""
        raw_email = """From: test@example.de
To: info@firma.de
Subject: Test Multipart
Content-Type: multipart/alternative; boundary="boundary123"

--boundary123
Content-Type: text/plain; charset=utf-8

Dies ist der Textinhalt.

--boundary123
Content-Type: text/html; charset=utf-8

<html><body><p>Dies ist der HTML-Inhalt.</p></body></html>

--boundary123--""".encode("utf-8")

        result = parser.parse(raw_email)

        assert result.subject == "Test Multipart"
        assert "Textinhalt" in result.text_body

    def test_parse_email_with_german_umlauts(self, parser):
        """Test parsing email with German special characters."""
        raw_email = """From: =?utf-8?Q?M=C3=BCller?= <mueller@example.de>
To: info@firma.de
Subject: =?utf-8?Q?R=C3=BCckfrage_zur_K=C3=BCche?=
Content-Type: text/plain; charset=utf-8

Größe der Küche: 20m²
Ansprechpartner: Jörg Schäfer
""".encode("utf-8")

        result = parser.parse(raw_email)

        assert "Müller" in (result.sender_name or "")
        assert "Küche" in result.subject
        assert "Küche" in result.plain_text

    def test_extract_customer_info_phone(self, parser):
        """Test extracting German phone numbers."""
        parsed = ParsedEmail(
            message_id="test",
            subject="Anfrage",
            sender_email="test@example.de",
            sender_name="Max",
            recipient_email="info@firma.de",
            recipient_name=None,
            plain_text="Bitte rufen Sie mich an: 0711-12345678 oder +49 176 98765432",
        )

        info = parser.extract_customer_info(parsed)

        assert info["phone"] is not None
        # Should match one of the phone numbers
        assert "0711" in info["phone"] or "176" in info["phone"]

    def test_extract_customer_info_address(self, parser):
        """Test extracting German addresses with PLZ."""
        parsed = ParsedEmail(
            message_id="test",
            subject="Anfrage",
            sender_email="test@example.de",
            sender_name="Max Müller",
            recipient_email="info@firma.de",
            recipient_name=None,
            plain_text="Meine Adresse: Musterstraße 123, 72379 Hechingen",
        )

        info = parser.extract_customer_info(parsed)

        assert info["plz"] == "72379"
        assert info["city"] == "Hechingen"
        assert info["name"] == "Max Müller"


# ============================================================================
# Email Classifier Tests
# ============================================================================


class TestEmailClassifier:
    """Tests for EmailClassifier service."""

    @pytest.fixture
    def classifier(self):
        """Create classifier without LLM (pattern-based)."""
        return EmailClassifier(api_key=None)

    def test_classify_repair_notfall(self, classifier):
        """Test classifying emergency repair request."""
        parsed = ParsedEmail(
            message_id="test",
            subject="NOTFALL: Heizung defekt!",
            sender_email="kunde@example.de",
            sender_name="Hans Schmidt",
            recipient_email="info@firma.de",
            recipient_name=None,
            plain_text="Hilfe! Die Heizung ist defekt und funktioniert nicht mehr. Es ist dringend!",
        )

        result = classifier._classify_with_patterns(parsed)

        assert result.task_type == "repairs"
        assert result.urgency in ["notfall", "dringend"]
        assert result.trade_category == "shk"

    def test_classify_quote_request(self, classifier):
        """Test classifying quote request."""
        parsed = ParsedEmail(
            message_id="test",
            subject="Bitte um Angebot",
            sender_email="kunde@example.de",
            sender_name="Maria Weber",
            recipient_email="info@firma.de",
            recipient_name=None,
            plain_text="Sehr geehrte Damen und Herren, wir bitten um ein Angebot fuer eine neue Heizungsanlage. Keine Eile, wir haben Zeit.",
        )

        result = classifier._classify_with_patterns(parsed)

        assert result.task_type == "quotes"
        # Quote requests with "keine eile" should be routine
        assert result.urgency in ["normal", "routine"]
        assert result.trade_category == "shk"

    def test_classify_complaint(self, classifier):
        """Test classifying complaint."""
        parsed = ParsedEmail(
            message_id="test",
            subject="Beschwerde über letzte Reparatur",
            sender_email="kunde@example.de",
            sender_name="Peter Meier",
            recipient_email="info@firma.de",
            recipient_name=None,
            plain_text="Ich bin sehr unzufrieden mit der letzten Reparatur. Der Techniker hat Pfusch gemacht und jetzt tropft es wieder.",
        )

        result = classifier._classify_with_patterns(parsed)

        assert result.task_type == "complaints"

    def test_classify_billing(self, classifier):
        """Test classifying billing inquiry."""
        parsed = ParsedEmail(
            message_id="test",
            subject="Frage zur Rechnung RE-2024-1234",
            sender_email="kunde@example.de",
            sender_name="Lisa Bauer",
            recipient_email="info@firma.de",
            recipient_name=None,
            plain_text="Sehr geehrte Damen und Herren, ich habe eine Frage zu meiner Rechnung. Könnten Sie mir die Bankverbindung für die Überweisung mitteilen?",
        )

        result = classifier._classify_with_patterns(parsed)

        assert result.task_type == "billing"
        assert result.urgency in ["normal", "routine"]

    def test_classify_appointment(self, classifier):
        """Test classifying appointment request."""
        parsed = ParsedEmail(
            message_id="test",
            subject="Terminverschiebung",
            sender_email="kunde@example.de",
            sender_name="Klaus Fischer",
            recipient_email="info@firma.de",
            recipient_name=None,
            plain_text="Guten Tag, leider muss ich den Termin am Montag absagen. Wann wäre ein neuer Termin möglich?",
        )

        result = classifier._classify_with_patterns(parsed)

        assert result.task_type == "appointment"

    def test_classify_elektro(self, classifier):
        """Test detecting elektro trade category."""
        parsed = ParsedEmail(
            message_id="test",
            subject="Steckdose defekt",
            sender_email="kunde@example.de",
            sender_name="Anna Schulz",
            recipient_email="info@firma.de",
            recipient_name=None,
            plain_text="In unserer Küche funktioniert eine Steckdose nicht mehr. Außerdem flackert das Licht im Wohnzimmer.",
        )

        result = classifier._classify_with_patterns(parsed)

        assert result.trade_category == "elektro"

    def test_classify_dringend_urgency(self, classifier):
        """Test detecting dringend urgency level."""
        parsed = ParsedEmail(
            message_id="test",
            subject="Dringend: Heizung geht nicht",
            sender_email="kunde@example.de",
            sender_name="Tom Werner",
            recipient_email="info@firma.de",
            recipient_name=None,
            plain_text="Bitte kommen Sie so schnell wie möglich, das Warmwasser geht nicht mehr!",
        )

        result = classifier._classify_with_patterns(parsed)

        assert result.urgency == "dringend"


# ============================================================================
# Email Encryption Tests
# ============================================================================


class TestEmailEncryption:
    """Tests for EmailEncryption utility."""

    def test_encrypt_decrypt(self):
        """Test basic encryption and decryption."""
        from cryptography.fernet import Fernet

        key = Fernet.generate_key()
        encryption = EmailEncryption(key=key)

        password = "super_secret_password_123"
        encrypted = encryption.encrypt(password)

        assert encrypted != password
        assert encryption.decrypt(encrypted) == password

    def test_different_keys_fail(self):
        """Test that decryption fails with wrong key."""
        from cryptography.fernet import Fernet, InvalidToken

        key1 = Fernet.generate_key()
        key2 = Fernet.generate_key()

        encryption1 = EmailEncryption(key=key1)
        encryption2 = EmailEncryption(key=key2)

        password = "test_password"
        encrypted = encryption1.encrypt(password)

        with pytest.raises(InvalidToken):
            encryption2.decrypt(encrypted)


# ============================================================================
# Email Config Tests
# ============================================================================


class TestEmailConfig:
    """Tests for EmailConfig dataclass."""

    def test_email_config_defaults(self):
        """Test EmailConfig default values."""
        config = EmailConfig(tenant_id="test-tenant")

        assert config.enabled is True
        assert config.imap_port == 993
        assert config.imap_use_ssl is True
        assert config.smtp_port == 587
        assert config.smtp_use_tls is True
        assert config.poll_interval_minutes == 2
        assert config.folder == "INBOX"
        assert config.mark_as_read is True
        assert config.send_auto_reply is True

    def test_email_config_custom(self):
        """Test EmailConfig with custom values."""
        config = EmailConfig(
            tenant_id="custom-tenant",
            enabled=False,
            imap_host="imap.custom.de",
            imap_port=143,
            imap_user="custom@custom.de",
            imap_password="encrypted_password",
            imap_use_ssl=False,
            poll_interval_minutes=5,
            folder="EINGANG",
            mark_as_read=False,
            move_to_folder="Bearbeitet",
            send_auto_reply=False,
        )

        assert config.tenant_id == "custom-tenant"
        assert config.enabled is False
        assert config.imap_host == "imap.custom.de"
        assert config.imap_port == 143
        assert config.imap_use_ssl is False
        assert config.poll_interval_minutes == 5
        assert config.folder == "EINGANG"


# ============================================================================
# Email Prompts Tests
# ============================================================================


class TestEmailPrompts:
    """Tests for email classification prompts."""

    def test_prompts_exist(self):
        """Test that all required prompts are defined."""
        from phone_agent.industry.handwerk.email_prompts import (
            EMAIL_CLASSIFICATION_SYSTEM_PROMPT,
            EMAIL_CLASSIFICATION_USER_PROMPT,
            EMAIL_AUTO_REPLY_TEMPLATES,
            TASK_TYPE_LABELS,
            URGENCY_LABELS,
            TRADE_CATEGORY_LABELS,
        )

        assert len(EMAIL_CLASSIFICATION_SYSTEM_PROMPT) > 500
        assert "{subject}" in EMAIL_CLASSIFICATION_USER_PROMPT
        assert "{body}" in EMAIL_CLASSIFICATION_USER_PROMPT

    def test_auto_reply_templates(self):
        """Test auto-reply templates."""
        from phone_agent.industry.handwerk.email_prompts import EMAIL_AUTO_REPLY_TEMPLATES

        assert "notfall" in EMAIL_AUTO_REPLY_TEMPLATES
        assert "dringend" in EMAIL_AUTO_REPLY_TEMPLATES
        assert "normal" in EMAIL_AUTO_REPLY_TEMPLATES
        assert "routine" in EMAIL_AUTO_REPLY_TEMPLATES
        assert EMAIL_AUTO_REPLY_TEMPLATES["spam"] is None

        # Check template placeholders
        notfall_template = EMAIL_AUTO_REPLY_TEMPLATES["notfall"]
        assert "{customer_name}" in notfall_template
        assert "{ticket_number}" in notfall_template
        assert "{company_name}" in notfall_template

    def test_labels_complete(self):
        """Test that all labels are defined."""
        from phone_agent.industry.handwerk.email_prompts import (
            TASK_TYPE_LABELS,
            URGENCY_LABELS,
            TRADE_CATEGORY_LABELS,
        )

        # Task types
        assert "repairs" in TASK_TYPE_LABELS
        assert "quotes" in TASK_TYPE_LABELS
        assert "complaints" in TASK_TYPE_LABELS
        assert "spam" in TASK_TYPE_LABELS

        # Urgency levels
        assert "notfall" in URGENCY_LABELS
        assert "dringend" in URGENCY_LABELS
        assert "normal" in URGENCY_LABELS
        assert "routine" in URGENCY_LABELS

        # Trade categories
        assert "shk" in TRADE_CATEGORY_LABELS
        assert "elektro" in TRADE_CATEGORY_LABELS
        assert "sanitaer" in TRADE_CATEGORY_LABELS


# ============================================================================
# Integration Tests (Async)
# ============================================================================


@pytest.mark.asyncio
class TestEmailClassifierAsync:
    """Async tests for EmailClassifier with mocked LLM."""

    async def test_classify_with_fallback(self):
        """Test classification falls back to patterns when LLM unavailable."""
        classifier = EmailClassifier(api_key=None)

        parsed = ParsedEmail(
            message_id="test",
            subject="Heizung kaputt",
            sender_email="kunde@example.de",
            sender_name="Test Kunde",
            recipient_email="info@firma.de",
            recipient_name=None,
            plain_text="Unsere Heizung ist kaputt und es ist dringend!",
        )

        result = await classifier.classify(parsed)

        assert result.task_type == "repairs"
        assert result.urgency in ["dringend", "notfall"]
        assert result.trade_category == "shk"
        assert result.confidence == 0.5  # Pattern matching confidence

    async def test_classify_with_mocked_llm(self):
        """Test classification with mocked LLM response."""
        classifier = EmailClassifier(api_key="fake_key")

        # Mock the LLM
        mock_response = """{
            "task_type": "repairs",
            "urgency": "dringend",
            "trade_category": "shk",
            "customer_info": {
                "name": "Max Müller",
                "phone": "0711-123456",
                "plz": "72379"
            },
            "summary": "Heizung ausgefallen, dringend",
            "confidence": 0.95,
            "needs_human_review": false
        }"""

        # Create mock LLM
        mock_llm = MagicMock()
        mock_llm.generate_async = AsyncMock(return_value=mock_response)
        mock_llm.is_loaded = True
        classifier._llm = mock_llm

        parsed = ParsedEmail(
            message_id="test",
            subject="Heizung kaputt",
            sender_email="kunde@example.de",
            sender_name="Max Müller",
            recipient_email="info@firma.de",
            recipient_name=None,
            plain_text="Unsere Heizung ist ausgefallen.",
        )

        result = await classifier.classify(parsed)

        assert result.task_type == "repairs"
        assert result.urgency == "dringend"
        assert result.trade_category == "shk"
        assert result.customer_name == "Max Müller"
        assert result.customer_phone == "0711-123456"
        assert result.confidence == 0.95


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================


class TestEmailParserEdgeCases:
    """Test edge cases in email parsing."""

    @pytest.fixture
    def parser(self):
        return EmailParser()

    def test_parse_empty_email(self, parser):
        """Test parsing email with minimal content."""
        raw_email = b"From: sender@example.de\nTo: recipient@example.de\nSubject:\nContent-Type: text/plain\n\n"
        result = parser.parse(raw_email)

        assert result.sender_email == "sender@example.de"
        assert result.subject == ""
        assert result.plain_text == ""

    def test_parse_email_without_subject(self, parser):
        """Test parsing email without subject line."""
        raw_email = b"From: sender@example.de\nTo: recipient@example.de\nContent-Type: text/plain\n\nSome content here."

        result = parser.parse(raw_email)

        assert result.subject == ""
        assert "content here" in result.plain_text

    def test_parse_email_with_attachment_metadata(self, parser):
        """Test that attachment metadata is extracted."""
        raw_email = """From: sender@example.de
To: recipient@example.de
Subject: With Attachment
Content-Type: multipart/mixed; boundary="boundary123"

--boundary123
Content-Type: text/plain

Email body text.

--boundary123
Content-Type: application/pdf
Content-Disposition: attachment; filename="document.pdf"

(binary content here)

--boundary123--""".encode("utf-8")

        result = parser.parse(raw_email)

        assert result.has_attachments is True
        assert len(result.attachments) == 1
        assert result.attachments[0].filename == "document.pdf"
        assert result.attachments[0].content_type == "application/pdf"


class TestEmailClassifierEdgeCases:
    """Test edge cases in email classification."""

    @pytest.fixture
    def classifier(self):
        return EmailClassifier(api_key=None)

    def test_classify_mixed_categories(self, classifier):
        """Test classification when multiple categories present."""
        parsed = ParsedEmail(
            message_id="test",
            subject="Heizung und Elektrik",
            sender_email="kunde@example.de",
            sender_name=None,
            recipient_email="info@firma.de",
            recipient_name=None,
            plain_text="Unsere Heizung funktioniert nicht und die Sicherung springt ständig raus.",
        )

        result = classifier._classify_with_patterns(parsed)

        # Should pick one category based on scoring
        assert result.trade_category in ["shk", "elektro", "allgemein"]

    def test_classify_spam(self, classifier):
        """Test spam detection."""
        parsed = ParsedEmail(
            message_id="test",
            subject="Newsletter abbestellen",
            sender_email="spam@example.de",
            sender_name=None,
            recipient_email="info@firma.de",
            recipient_name=None,
            plain_text="Bitte den Newsletter abbestellen. Diese Werbung ist unerwuenscht.",
        )

        result = classifier._classify_with_patterns(parsed)

        assert result.task_type == "spam"
        assert result.urgency in ["normal", "routine"]
