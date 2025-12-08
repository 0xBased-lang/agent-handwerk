"""Application configuration."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DialectSettings(BaseModel):
    """German dialect detection and routing configuration."""

    # Enable dialect-aware routing for German
    enabled: bool = True

    # Detection mode: "text" (faster, post-transcription), "audio" (pre-transcription probe)
    # "text" mode uses transcribed text patterns, avoiding double transcription
    detection_mode: str = "text"

    # Probe duration for dialect detection (seconds) - only used in "audio" mode
    probe_duration: float = 1.5  # Reduced from 3.0 for faster detection

    # Minimum confidence to use dialect-specific model
    confidence_threshold: float = 0.6

    # Maximum models to keep loaded simultaneously
    max_loaded_models: int = 2

    # Dialect-specific models (HuggingFace paths)
    models: dict[str, str] = {
        "de_standard": "primeline/whisper-large-v3-german",
        "de_alemannic": "Flurin17/whisper-large-v3-turbo-swiss-german",
        "de_bavarian": "openai/whisper-large-v3",
        "de_low": "openai/whisper-large-v3",
    }

    # Preload specific dialects on startup (empty = lazy loading)
    preload_dialects: list[str] = []


class AISTTSettings(BaseModel):
    """Speech-to-text configuration."""

    # Default model (used when dialect detection disabled)
    model: str = "openai/whisper-large-v3"
    model_path: str = "models/whisper"
    device: str = "cpu"
    compute_type: str = "int8"
    language: str = "de"  # Default language (None for auto-detection)
    beam_size: int = 5
    vad_filter: bool = True

    # German dialect routing
    dialect: DialectSettings = Field(default_factory=DialectSettings)


class AILLMSettings(BaseModel):
    """Language model configuration."""

    model: str = "llama-3.2-1b-instruct-q4_k_m.gguf"
    model_path: str = "models/llm"
    n_ctx: int = 2048
    n_threads: int = 4
    n_gpu_layers: int = 0
    temperature: float = 0.7
    max_tokens: int = 256


class AITTSSettings(BaseModel):
    """Text-to-speech configuration."""

    model: str = "de_DE-thorsten-medium"
    model_path: str = "models/tts"
    speaker_id: int = 0
    sample_rate: int = 22050

    # Language-specific voices (Piper TTS)
    voices: dict[str, str] = {
        "de": "de_DE-thorsten-medium",
        "tr": "tr_TR-dfki-medium",
        "ru": "ru_RU-denis-medium",
    }

    # Maximum voice models to cache simultaneously
    max_cached_voices: int = 2

    # Preload voices on startup (empty = lazy loading)
    preload_voices: list[str] = []


class CloudAISettings(BaseModel):
    """Cloud AI provider configuration.

    Supports Groq (LLM), Deepgram (STT), and ElevenLabs (TTS).
    Set enabled=True and provider to switch from local to cloud.
    """

    # Master switch
    enabled: bool = False

    # Provider mode: local, cloud, hybrid (cloud LLM only)
    provider: str = "local"

    # Fallback to local providers on cloud errors
    fallback_to_local: bool = True

    # Groq LLM settings
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    # Deepgram STT settings
    deepgram_api_key: str = ""
    deepgram_model: str = "nova-2"

    # ElevenLabs TTS settings
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = "pNInz6obpgDQGcFmaJgB"  # Adam
    elevenlabs_model: str = "eleven_flash_v2_5"


class LanguageDetectionSettings(BaseModel):
    """Language detection configuration."""

    enabled: bool = True
    model: str = "speechbrain/lang-id-voxlingua107-ecapa"
    confidence_threshold: float = 0.7
    fallback_language: str = "de"

    # Load model eagerly on startup (vs lazy on first use)
    eager_load: bool = False


class LanguageSettings(BaseModel):
    """Multilingual support configuration."""

    default: str = "de"
    supported: list[str] = ["de", "tr", "ru"]
    detection: LanguageDetectionSettings = Field(default_factory=LanguageDetectionSettings)


class AISettings(BaseModel):
    """AI subsystem configuration."""

    stt: AISTTSettings = Field(default_factory=AISTTSettings)
    llm: AILLMSettings = Field(default_factory=AILLMSettings)
    tts: AITTSSettings = Field(default_factory=AITTSSettings)
    language: LanguageSettings = Field(default_factory=LanguageSettings)
    cloud: CloudAISettings = Field(default_factory=CloudAISettings)


class SIPSettings(BaseModel):
    """SIP telephony configuration."""

    server: str = ""
    username: str = ""
    password: str = ""
    port: int = 5060


class AudioSettings(BaseModel):
    """Audio device configuration."""

    input_device: str = "default"
    output_device: str = "default"
    sample_rate: int = 16000
    channels: int = 1


class FreeSwitchSettings(BaseModel):
    """FreeSWITCH ESL configuration."""

    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 8021
    password: str = ""  # REQUIRED if enabled - no default for security
    reconnect: bool = True
    reconnect_delay: float = 5.0
    max_reconnect_attempts: int = 10


class TwilioSettings(BaseModel):
    """Twilio integration configuration."""

    enabled: bool = False
    account_sid: str = ""
    auth_token: str = ""
    from_number: str = ""
    twiml_app_sid: str = ""
    webhook_url: str = ""
    # SMS-specific settings
    messaging_service_sid: str = ""  # Optional Messaging Service for advanced routing


class SipgateSettings(BaseModel):
    """sipgate integration configuration."""

    enabled: bool = False
    username: str = ""
    password: str = ""
    api_token: str = ""
    caller_id: str = ""


class WebhookSettings(BaseModel):
    """Webhook security configuration."""

    validate_signatures: bool = True
    # IP validation - recommended to enable in production for additional security
    # Validates that webhooks come from known provider IP ranges (Twilio, sipgate)
    validate_ip: bool = False
    timestamp_tolerance_seconds: int = 300


class TelephonySettings(BaseModel):
    """Telephony subsystem configuration."""

    enabled: bool = False
    sip: SIPSettings = Field(default_factory=SIPSettings)
    audio: AudioSettings = Field(default_factory=AudioSettings)
    freeswitch: FreeSwitchSettings = Field(default_factory=FreeSwitchSettings)
    twilio: TwilioSettings = Field(default_factory=TwilioSettings)
    sipgate: SipgateSettings = Field(default_factory=SipgateSettings)
    webhooks: WebhookSettings = Field(default_factory=WebhookSettings)


class DatabaseSettings(BaseModel):
    """Database configuration."""

    url: str = "sqlite+aiosqlite:///data/phone_agent.db"
    echo: bool = False


class TriageLevel(BaseModel):
    """Triage urgency level definition."""

    name: str
    description: str
    action: str


class TriageSettings(BaseModel):
    """Triage configuration."""

    urgency_levels: list[TriageLevel] = Field(default_factory=list)


class IndustrySettings(BaseModel):
    """Industry-specific configuration."""

    name: str = "gesundheit"
    display_name: str = "Gesundheit (Ambulant)"
    features: dict[str, bool] = Field(default_factory=dict)
    triage: TriageSettings = Field(default_factory=TriageSettings)
    hours: dict[str, str | None] = Field(default_factory=dict)


class PVSSettings(BaseModel):
    """Practice management system configuration."""

    enabled: bool = False
    type: str = "cgm"
    api_url: str = ""
    api_key: str = ""


class SMSSettings(BaseModel):
    """SMS gateway configuration."""

    enabled: bool = False
    provider: str = "sipgate"
    api_url: str = ""
    api_key: str = ""


class SMTPSettings(BaseModel):
    """SMTP email configuration."""

    host: str = ""
    port: int = 587
    username: str = ""
    password: str = ""
    use_tls: bool = True
    use_ssl: bool = False


class SendGridSettings(BaseModel):
    """SendGrid email configuration."""

    api_key: str = ""
    webhook_url: str = ""


class EmailSettings(BaseModel):
    """Email gateway configuration."""

    enabled: bool = False
    provider: str = "smtp"  # smtp, sendgrid, mock
    from_email: str = ""
    from_name: str = ""
    reply_to: str = ""
    smtp: SMTPSettings = Field(default_factory=SMTPSettings)
    sendgrid: SendGridSettings = Field(default_factory=SendGridSettings)


class GoogleCalendarSettings(BaseModel):
    """Google Calendar integration settings."""

    # Authentication - use either credentials_file or credentials_json
    credentials_file: str = ""  # Path to service account JSON file
    credentials_json: str = ""  # JSON string from environment variable

    # Calendar settings
    calendar_id: str = "primary"  # Calendar ID or email address

    # Business hours (used for slot generation)
    business_hours_start: str = "08:00"
    business_hours_end: str = "18:00"
    lunch_start: str = "12:00"
    lunch_end: str = "13:00"
    working_days: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4])

    # Scheduling settings
    default_slot_duration: int = 15
    max_advance_days: int = 30

    # Rate limiting and caching
    max_retries: int = 3
    retry_base_delay: float = 1.0
    cache_ttl_seconds: int = 30


class CalendarSettings(BaseModel):
    """Calendar configuration."""

    enabled: bool = True
    type: str = "local"  # local, google, mock
    timezone: str = "Europe/Berlin"
    google: GoogleCalendarSettings = Field(default_factory=GoogleCalendarSettings)


class IntegrationsSettings(BaseModel):
    """External integrations configuration."""

    pvs: PVSSettings = Field(default_factory=PVSSettings)
    sms: SMSSettings = Field(default_factory=SMSSettings)
    email: EmailSettings = Field(default_factory=EmailSettings)
    calendar: CalendarSettings = Field(default_factory=CalendarSettings)


class Settings(BaseSettings):
    """Application settings.

    Loaded from:
    1. Environment variables (ITF_*)
    2. configs/{environment}.yaml
    3. configs/default.yaml
    """

    model_config = SettingsConfigDict(
        env_prefix="ITF_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    # Device identification
    device_id: str = ""
    device_name: str = "phone-agent-dev"

    # Environment
    environment: str = "development"
    debug: bool = True

    # Logging
    log_level: str = "INFO"
    log_json: bool = False

    # API Server
    api_host: str = "0.0.0.0"
    api_port: int = 8080

    # JWT Authentication
    jwt_secret_key: str = ""  # MUST be set in production!
    jwt_expiry_minutes: int = 60
    jwt_algorithm: str = "HS256"

    # AI Model Loading
    preload_ai_models: bool = False  # Set to True to preload models at startup

    # Remote Management
    remote_enabled: bool = True
    heartbeat_interval: int = 60
    heartbeat_endpoint: str | None = None

    # Subsystems
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    ai: AISettings = Field(default_factory=AISettings)
    telephony: TelephonySettings = Field(default_factory=TelephonySettings)
    industry: IndustrySettings = Field(default_factory=IndustrySettings)
    integrations: IntegrationsSettings = Field(default_factory=IntegrationsSettings)

    # Convenience properties for webhook security
    @property
    def webhook_validate_signatures(self) -> bool:
        """Whether to validate webhook signatures."""
        return self.telephony.webhooks.validate_signatures

    @property
    def twilio_auth_token(self) -> str | None:
        """Twilio auth token for signature validation."""
        return self.telephony.twilio.auth_token or None

    @property
    def sipgate_api_token(self) -> str | None:
        """sipgate API token for signature validation."""
        return self.telephony.sipgate.api_token or None


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings.

    Returns:
        Settings object loaded from config files and environment.
    """
    import os
    from dynaconf import Dynaconf

    # Determine paths
    config_dir = Path("configs")
    env = os.getenv("ITF_ENV", "development")

    # Build settings file list
    settings_files = []
    if (config_dir / "default.yaml").exists():
        settings_files.append(str(config_dir / "default.yaml"))
    if (config_dir / f"{env}.yaml").exists():
        settings_files.append(str(config_dir / f"{env}.yaml"))

    # Load with Dynaconf
    dynaconf = Dynaconf(
        envvar_prefix="ITF",
        settings_files=settings_files,
        load_dotenv=True,
    )

    # Convert to dict
    config_dict: dict[str, Any] = {}
    for key in dynaconf.keys():
        if not key.startswith("_"):
            value = dynaconf[key]
            config_dict[key.lower()] = value

    # Add environment
    config_dict["environment"] = env

    # Generate device_id if not set
    if not config_dict.get("device_id"):
        config_dict["device_id"] = _generate_device_id()

    return Settings(**config_dict)


def _generate_device_id() -> str:
    """Generate a unique device ID from Raspberry Pi serial or hostname."""
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("Serial"):
                    return f"pi-{line.split(':')[1].strip()[-8:]}"
    except (FileNotFoundError, IndexError):
        pass

    import socket

    return f"dev-{socket.gethostname()}"


def validate_production_settings(settings: Settings) -> list[str]:
    """Validate settings for production readiness.

    Args:
        settings: Application settings to validate.

    Returns:
        List of validation error messages (empty if all valid).
    """
    errors: list[str] = []

    # Only enforce strict validation in production
    if settings.environment not in ("production", "staging", "prod"):
        return errors

    # JWT secret required
    if not settings.jwt_secret_key:
        errors.append(
            "ITF_JWT_SECRET_KEY must be set in production"
        )

    # FreeSWITCH password required if enabled
    if settings.telephony.freeswitch.enabled:
        if not settings.telephony.freeswitch.password:
            errors.append(
                "ITF_TELEPHONY__FREESWITCH__PASSWORD must be set when FreeSWITCH is enabled"
            )

    # Twilio auth token required if enabled
    if settings.telephony.twilio.enabled:
        if not settings.telephony.twilio.auth_token:
            errors.append(
                "ITF_TELEPHONY__TWILIO__AUTH_TOKEN must be set when Twilio is enabled"
            )
        if not settings.telephony.twilio.account_sid:
            errors.append(
                "ITF_TELEPHONY__TWILIO__ACCOUNT_SID must be set when Twilio is enabled"
            )

    # sipgate token required if enabled
    if settings.telephony.sipgate.enabled:
        if not settings.telephony.sipgate.api_token:
            errors.append(
                "ITF_TELEPHONY__SIPGATE__API_TOKEN must be set when sipgate is enabled"
            )

    return errors


def require_valid_settings() -> Settings:
    """Get settings and raise if production validation fails.

    Raises:
        ValueError: If production settings are invalid.

    Returns:
        Validated settings.
    """
    settings = get_settings()
    errors = validate_production_settings(settings)

    if errors:
        error_list = "\n  - ".join(errors)
        raise ValueError(
            f"Production configuration errors:\n  - {error_list}"
        )

    return settings
