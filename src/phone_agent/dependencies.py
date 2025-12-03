"""Dependency Injection for Phone Agent.

Provides FastAPI dependency functions for services and components.
Ensures proper lifecycle management and testability.

Thread Safety:
    All singleton factories use threading.Lock() to prevent race conditions
    during concurrent initialization. This is safe for both sync and async contexts.

Usage:
    from phone_agent.dependencies import get_telephony_service

    @router.get("/endpoint")
    async def handler(service: TelephonyService = Depends(get_telephony_service)):
        ...
"""

from __future__ import annotations

import threading
from functools import lru_cache
from typing import Annotated, AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from phone_agent.config import Settings, get_settings
from phone_agent.db.session import get_db as _get_db, get_db_context


# =============================================================================
# Thread-Safe Singleton Locks
# =============================================================================

_telephony_lock = threading.Lock()
_sip_lock = threading.Lock()
_freeswitch_lock = threading.Lock()
_stt_lock = threading.Lock()
_llm_lock = threading.Lock()
_tts_lock = threading.Lock()
_language_detector_lock = threading.Lock()
_dialect_stt_lock = threading.Lock()
_security_lock = threading.Lock()


# =============================================================================
# Settings Dependency
# =============================================================================


def get_app_settings() -> Settings:
    """Get application settings.

    Returns cached settings instance.
    """
    return get_settings()


SettingsDep = Annotated[Settings, Depends(get_app_settings)]


# =============================================================================
# Database Dependencies
# =============================================================================


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get database session for request.

    Yields session that auto-commits on success, rolls back on error.
    """
    async for session in _get_db():
        yield session


DatabaseDep = Annotated[AsyncSession, Depends(get_db)]


# =============================================================================
# Telephony Service Dependencies
# =============================================================================


# Cached service instances
_telephony_service_instance = None
_sip_client_instance = None
_freeswitch_client_instance = None


def get_telephony_service():
    """Get telephony service singleton.

    Thread-safe via double-checked locking pattern.

    Returns:
        TelephonyService instance
    """
    global _telephony_service_instance

    if _telephony_service_instance is None:
        with _telephony_lock:
            # Double-check after acquiring lock
            if _telephony_service_instance is None:
                from phone_agent.telephony.service import TelephonyService
                _telephony_service_instance = TelephonyService()

    return _telephony_service_instance


def get_sip_client():
    """Get SIP client singleton.

    Thread-safe via double-checked locking pattern.

    Returns:
        SIPClient instance or None if not configured
    """
    global _sip_client_instance

    if _sip_client_instance is None:
        with _sip_lock:
            if _sip_client_instance is None:
                settings = get_settings()
                if settings.telephony.sip.server:
                    from phone_agent.telephony.sip_client import SIPClient, SIPConfig

                    _sip_client_instance = SIPClient(
                        SIPConfig(
                            server=settings.telephony.sip.server,
                            username=settings.telephony.sip.username,
                            password=settings.telephony.sip.password,
                            port=settings.telephony.sip.port,
                        )
                    )

    return _sip_client_instance


def get_freeswitch_client():
    """Get FreeSWITCH client singleton.

    Thread-safe via double-checked locking pattern.

    Returns:
        FreeSwitchClient instance or None if not configured
    """
    global _freeswitch_client_instance

    if _freeswitch_client_instance is None:
        with _freeswitch_lock:
            if _freeswitch_client_instance is None:
                settings = get_settings()
                if settings.telephony.freeswitch.enabled:
                    from phone_agent.telephony.freeswitch import (
                        FreeSwitchClient,
                        FreeSwitchConfig,
                    )

                    _freeswitch_client_instance = FreeSwitchClient(
                        FreeSwitchConfig(
                            host=settings.telephony.freeswitch.host,
                            port=settings.telephony.freeswitch.port,
                            password=settings.telephony.freeswitch.password,
                        )
                    )

    return _freeswitch_client_instance


# Type aliases for dependency injection
TelephonyServiceDep = Annotated[object, Depends(get_telephony_service)]


# =============================================================================
# AI Model Dependencies
# =============================================================================


_stt_instance = None
_llm_instance = None
_tts_instance = None


def get_stt():
    """Get Speech-to-Text instance.

    Thread-safe via double-checked locking pattern.
    Returns lazy-loading STT engine.
    """
    global _stt_instance

    if _stt_instance is None:
        with _stt_lock:
            if _stt_instance is None:
                from phone_agent.ai.stt import SpeechToText

                settings = get_settings()
                _stt_instance = SpeechToText(
                    model=settings.ai.stt.model,
                    model_path=settings.ai.stt.model_path,
                    device=settings.ai.stt.device,
                    compute_type=settings.ai.stt.compute_type,
                    language=settings.ai.stt.language,
                    beam_size=settings.ai.stt.beam_size,
                    vad_filter=settings.ai.stt.vad_filter,
                )

    return _stt_instance


def get_llm():
    """Get Language Model instance.

    Thread-safe via double-checked locking pattern.
    Returns lazy-loading LLM engine.
    """
    global _llm_instance

    if _llm_instance is None:
        with _llm_lock:
            if _llm_instance is None:
                from phone_agent.ai.llm import LanguageModel

                settings = get_settings()
                _llm_instance = LanguageModel(
                    model=settings.ai.llm.model,
                    model_path=settings.ai.llm.model_path,
                    n_ctx=settings.ai.llm.n_ctx,
                    n_threads=settings.ai.llm.n_threads,
                    n_gpu_layers=settings.ai.llm.n_gpu_layers,
                    temperature=settings.ai.llm.temperature,
                    max_tokens=settings.ai.llm.max_tokens,
                )

    return _llm_instance


def get_tts():
    """Get Text-to-Speech instance.

    Thread-safe via double-checked locking pattern.
    Returns lazy-loading TTS engine with LRU voice caching.
    """
    global _tts_instance

    if _tts_instance is None:
        with _tts_lock:
            if _tts_instance is None:
                from phone_agent.ai.tts import TextToSpeech

                settings = get_settings()
                _tts_instance = TextToSpeech(
                    model=settings.ai.tts.model,
                    model_path=settings.ai.tts.model_path,
                    speaker_id=settings.ai.tts.speaker_id,
                    sample_rate=settings.ai.tts.sample_rate,
                    voices=settings.ai.tts.voices,
                    max_cached_voices=settings.ai.tts.max_cached_voices,
                )

                # Preload voices if configured
                if settings.ai.tts.preload_voices:
                    _tts_instance.preload_voices(settings.ai.tts.preload_voices)

    return _tts_instance


# Language Detection
_language_detector_instance = None


def get_language_detector():
    """Get Language Detector instance.

    Thread-safe via double-checked locking pattern.
    Returns lazy-loading language detection engine.
    """
    global _language_detector_instance

    if _language_detector_instance is None:
        with _language_detector_lock:
            if _language_detector_instance is None:
                from phone_agent.ai.language_detector import LanguageDetector

                settings = get_settings()
                _language_detector_instance = LanguageDetector(
                    model=settings.ai.language.detection.model,
                    supported_languages=settings.ai.language.supported,
                )

    return _language_detector_instance


# Dialect-Aware STT
_dialect_stt_instance = None


def get_dialect_aware_stt():
    """Get Dialect-Aware STT instance.

    Thread-safe via double-checked locking pattern.
    Returns lazy-loading STT with German dialect routing.
    Routes to specialized models based on detected dialect:
    - Standard German → primeline/whisper-large-v3-german
    - Alemannic (Schwäbisch) → Swiss German model
    """
    global _dialect_stt_instance

    if _dialect_stt_instance is None:
        with _dialect_stt_lock:
            if _dialect_stt_instance is None:
                from phone_agent.ai.stt_router import DialectAwareSTT

                settings = get_settings()
                dialect_config = settings.ai.stt.dialect

                _dialect_stt_instance = DialectAwareSTT(
                    model_path=settings.ai.stt.model_path,
                    device=settings.ai.stt.device,
                    compute_type=settings.ai.stt.compute_type,
                    beam_size=settings.ai.stt.beam_size,
                    vad_filter=settings.ai.stt.vad_filter,
                    max_loaded_models=dialect_config.max_loaded_models,
                    dialect_detection=dialect_config.enabled,
                    detection_mode=dialect_config.detection_mode,
                    probe_duration=dialect_config.probe_duration,
                )

                # Preload requested dialects
                if dialect_config.preload_dialects:
                    _dialect_stt_instance.preload_dialects(dialect_config.preload_dialects)

    return _dialect_stt_instance


# Type aliases
STTDep = Annotated[object, Depends(get_stt)]
DialectSTTDep = Annotated[object, Depends(get_dialect_aware_stt)]
LLMDep = Annotated[object, Depends(get_llm)]
TTSDep = Annotated[object, Depends(get_tts)]
LanguageDetectorDep = Annotated[object, Depends(get_language_detector)]


# =============================================================================
# Webhook Security Dependencies
# =============================================================================


_security_manager = None


def get_webhook_security():
    """Get webhook security manager.

    Thread-safe via double-checked locking pattern.

    Returns:
        WebhookSecurityManager instance
    """
    global _security_manager

    if _security_manager is None:
        with _security_lock:
            if _security_manager is None:
                from phone_agent.api.webhook_security import (
                    WebhookSecurityConfig,
                    WebhookSecurityManager,
                )

                settings = get_settings()
                config = WebhookSecurityConfig(
                    validate_signatures=settings.webhook_validate_signatures,
                    twilio_auth_token=settings.twilio_auth_token or "",
                    sipgate_api_token=settings.sipgate_api_token or "",
                )
                _security_manager = WebhookSecurityManager(config)

    return _security_manager


WebhookSecurityDep = Annotated[object, Depends(get_webhook_security)]


# =============================================================================
# Repository Dependencies
# =============================================================================


def get_call_repository(db: DatabaseDep):
    """Get call repository.

    Args:
        db: Database session from dependency injection

    Returns:
        CallRepository instance
    """
    from phone_agent.db.repositories.call_repo import CallRepository
    return CallRepository(db)


def get_appointment_repository(db: DatabaseDep):
    """Get appointment repository.

    Args:
        db: Database session from dependency injection

    Returns:
        AppointmentRepository instance
    """
    from phone_agent.db.repositories.appointment_repo import AppointmentRepository
    return AppointmentRepository(db)


def get_contact_repository(db: DatabaseDep):
    """Get contact repository.

    Args:
        db: Database session from dependency injection

    Returns:
        ContactRepository instance
    """
    from phone_agent.db.repositories.contact_repo import ContactRepository
    return ContactRepository(db)


# =============================================================================
# Service Dependencies
# =============================================================================


def get_recall_service(db: DatabaseDep):
    """Get recall service.

    Args:
        db: Database session from dependency injection

    Returns:
        RecallService instance
    """
    from phone_agent.services.recall_service import RecallService
    return RecallService(db)


# =============================================================================
# Cleanup Functions
# =============================================================================


async def cleanup_dependencies() -> None:
    """Clean up all cached dependencies.

    Call during application shutdown.
    """
    global _telephony_service_instance, _sip_client_instance
    global _freeswitch_client_instance
    global _stt_instance, _llm_instance, _tts_instance
    global _dialect_stt_instance, _language_detector_instance
    global _security_manager

    # Stop telephony service
    from itf_shared import get_logger
    log = get_logger(__name__)

    if _telephony_service_instance is not None:
        try:
            await _telephony_service_instance.stop()
        except Exception as e:
            log.warning("Error stopping telephony service during cleanup", error=str(e))
        _telephony_service_instance = None

    # Stop SIP client
    if _sip_client_instance is not None:
        try:
            await _sip_client_instance.stop()
        except Exception as e:
            log.warning("Error stopping SIP client during cleanup", error=str(e))
        _sip_client_instance = None

    # Disconnect FreeSWITCH
    if _freeswitch_client_instance is not None:
        try:
            await _freeswitch_client_instance.disconnect()
        except Exception as e:
            log.warning("Error disconnecting FreeSWITCH during cleanup", error=str(e))
        _freeswitch_client_instance = None

    # Unload AI models
    if _stt_instance is not None:
        try:
            _stt_instance.unload()
        except Exception as e:
            log.warning("Error unloading STT model during cleanup", error=str(e))
        _stt_instance = None

    if _llm_instance is not None:
        try:
            _llm_instance.unload()
        except Exception as e:
            log.warning("Error unloading LLM model during cleanup", error=str(e))
        _llm_instance = None

    if _tts_instance is not None:
        try:
            _tts_instance.unload()
        except Exception as e:
            log.warning("Error unloading TTS model during cleanup", error=str(e))
        _tts_instance = None

    # Unload dialect-aware STT (includes probe model)
    if _dialect_stt_instance is not None:
        try:
            _dialect_stt_instance.unload_all()
        except Exception as e:
            log.warning("Error unloading dialect STT during cleanup", error=str(e))
        _dialect_stt_instance = None

    # Unload language detector
    if _language_detector_instance is not None:
        try:
            _language_detector_instance.unload()
        except Exception as e:
            log.warning("Error unloading language detector during cleanup", error=str(e))
        _language_detector_instance = None

    _security_manager = None


def reset_dependencies() -> None:
    """Reset all cached dependencies (for testing).

    Does not clean up resources, just clears references.
    """
    global _telephony_service_instance, _sip_client_instance
    global _freeswitch_client_instance
    global _stt_instance, _llm_instance, _tts_instance
    global _dialect_stt_instance, _language_detector_instance
    global _security_manager

    _telephony_service_instance = None
    _sip_client_instance = None
    _freeswitch_client_instance = None
    _stt_instance = None
    _llm_instance = None
    _tts_instance = None
    _dialect_stt_instance = None
    _language_detector_instance = None
    _security_manager = None
