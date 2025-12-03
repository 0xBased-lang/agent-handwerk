"""Webhook endpoints for telephony integration.

Provides REST API endpoints for external SIP systems to notify
the Phone Agent of call events and stream audio.

Supported webhook providers:
- Twilio (with Media Streams)
- sipgate (German VoIP)
- Generic SIP

Security:
- All webhooks validate signatures from providers
- See webhook_security.py for implementation details
"""

from __future__ import annotations

import base64
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator

from itf_shared import get_logger

from .webhook_security import (
    WebhookSecurityConfig,
    WebhookSecurityManager,
    WebhookSecurityError,
)

log = get_logger(__name__)

router = APIRouter()

# Use dependency injection for services
from phone_agent.dependencies import get_webhook_security, get_telephony_service


def get_security_manager() -> WebhookSecurityManager:
    """Get webhook security manager via DI.

    Deprecated: Use get_webhook_security from dependencies instead.
    """
    return get_webhook_security()


async def validate_generic_webhook(request: Request) -> None:
    """Dependency to validate generic webhook HMAC signature.

    Validates the X-Signature header against the request body.
    Raises HTTPException 403 if validation fails.

    Usage:
        @router.post("/webhooks/call/incoming")
        async def handle_incoming_call(
            payload: IncomingCallWebhook,
            _: None = Depends(validate_generic_webhook),
        ):
            ...
    """
    try:
        security = get_security_manager()
        await security.validate_generic(request)
    except WebhookSecurityError as e:
        log.warning(
            "Invalid generic webhook signature",
            path=str(request.url.path),
            error=str(e),
        )
        raise HTTPException(status_code=403, detail="Invalid signature")


# Request/Response Models
# Size limits to prevent OOM attacks from large payloads

# Maximum sizes
MAX_CALL_ID_LENGTH = 256
MAX_PHONE_NUMBER_LENGTH = 32
MAX_STRING_FIELD_LENGTH = 1024
MAX_METADATA_KEYS = 50
MAX_METADATA_VALUE_LENGTH = 4096
MAX_AUDIO_BASE64_LENGTH = 1024 * 1024 * 10  # 10MB of base64 (~7.5MB audio)


class IncomingCallWebhook(BaseModel):
    """Incoming call webhook payload."""

    call_id: str = Field(
        ..., description="External call ID", max_length=MAX_CALL_ID_LENGTH
    )
    caller_id: str = Field(
        ..., description="Caller phone number", max_length=MAX_PHONE_NUMBER_LENGTH
    )
    callee_id: str = Field(
        ..., description="Called phone number", max_length=MAX_PHONE_NUMBER_LENGTH
    )
    direction: str = Field(default="inbound", max_length=32)
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(), max_length=64
    )
    provider: str = Field(default="generic", max_length=64)
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description=f"Additional metadata (max {MAX_METADATA_KEYS} keys)",
    )

    @field_validator("metadata")
    @classmethod
    def validate_metadata_size(cls, v: dict[str, Any]) -> dict[str, Any]:
        """Validate metadata size constraints."""
        if len(v) > MAX_METADATA_KEYS:
            raise ValueError(f"metadata cannot have more than {MAX_METADATA_KEYS} keys")
        return v


class CallEventWebhook(BaseModel):
    """Call event webhook payload."""

    call_id: str = Field(
        ..., description="External call ID", max_length=MAX_CALL_ID_LENGTH
    )
    event: str = Field(..., description="Event type", max_length=64)
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(), max_length=64
    )
    data: dict[str, Any] = Field(
        default_factory=dict,
        description=f"Event data (max {MAX_METADATA_KEYS} keys)",
    )

    @field_validator("data")
    @classmethod
    def validate_data_size(cls, v: dict[str, Any]) -> dict[str, Any]:
        """Validate data size constraints."""
        if len(v) > MAX_METADATA_KEYS:
            raise ValueError(f"data cannot have more than {MAX_METADATA_KEYS} keys")
        return v


class AudioWebhook(BaseModel):
    """Audio data webhook payload."""

    call_id: str = Field(..., max_length=MAX_CALL_ID_LENGTH)
    audio_base64: str = Field(
        ...,
        description="Base64 encoded audio",
        max_length=MAX_AUDIO_BASE64_LENGTH,
    )
    sample_rate: int = Field(default=16000, ge=8000, le=48000)
    format: str = Field(default="pcm", max_length=32)


class WebhookResponse(BaseModel):
    """Standard webhook response."""

    success: bool
    call_id: str | None = None
    action: str | None = None
    audio_bridge: dict[str, Any] | None = None
    message: str | None = None


# Telephony service is now provided via dependencies.get_telephony_service()


# Webhook Endpoints

@router.post("/webhooks/call/incoming", response_model=WebhookResponse)
async def handle_incoming_call(
    request: Request,
    payload: IncomingCallWebhook,
    _: None = Depends(validate_generic_webhook),
) -> WebhookResponse:
    """Handle incoming call webhook.

    Called by external SIP system when a new call arrives.
    Requires valid HMAC signature in X-Signature header.

    Returns instructions for handling the call.
    """
    log.info(
        "Incoming call webhook",
        call_id=payload.call_id,
        caller=payload.caller_id,
        provider=payload.provider,
    )

    try:
        service = get_telephony_service()
        result = await service.handle_webhook_incoming(
            call_id=payload.call_id,
            caller_id=payload.caller_id,
            callee_id=payload.callee_id,
            metadata=payload.metadata,
        )

        return WebhookResponse(
            success=True,
            call_id=result.get("internal_call_id"),
            action=result.get("action"),
            audio_bridge=result.get("audio_bridge"),
        )

    except Exception as e:
        log.error("Incoming call webhook failed", error=str(e))
        return WebhookResponse(
            success=False,
            message=str(e),
        )


@router.post("/webhooks/call/hangup", response_model=WebhookResponse)
async def handle_hangup(
    request: Request,
    payload: CallEventWebhook,
    _: None = Depends(validate_generic_webhook),
) -> WebhookResponse:
    """Handle call hangup webhook.

    Called when a call ends.
    Requires valid HMAC signature in X-Signature header.
    """
    log.info("Hangup webhook", call_id=payload.call_id)

    try:
        service = get_telephony_service()
        result = await service.handle_webhook_hangup(payload.call_id)

        return WebhookResponse(
            success=result.get("success", False),
            action="hangup",
        )

    except Exception as e:
        log.error("Hangup webhook failed", error=str(e))
        return WebhookResponse(
            success=False,
            message=str(e),
        )


@router.post("/webhooks/call/event", response_model=WebhookResponse)
async def handle_call_event(
    request: Request,
    payload: CallEventWebhook,
    _: None = Depends(validate_generic_webhook),
) -> WebhookResponse:
    """Handle generic call event webhook.

    Requires valid HMAC signature in X-Signature header.

    Supports various events:
    - ringing: Call is ringing on agent side
    - answered: Call was answered
    - on_hold: Call placed on hold
    - resumed: Call resumed from hold
    - dtmf: DTMF digit received
    - recording_started: Recording started
    - recording_stopped: Recording stopped
    """
    log.info(
        "Call event webhook",
        call_id=payload.call_id,
        event_type=payload.event,
    )

    service = get_telephony_service()
    event_type = payload.event.lower()

    try:
        # Process event based on type
        if event_type == "ringing":
            # Call is ringing - update call state
            log.debug("Call ringing", call_id=payload.call_id)
            return WebhookResponse(
                success=True,
                action="ringing_acknowledged",
            )

        elif event_type == "answered":
            # Call was answered - transition to active conversation
            log.info("Call answered", call_id=payload.call_id)
            if service.call_handler.is_in_call:
                # Already handled via incoming webhook, just acknowledge
                pass
            return WebhookResponse(
                success=True,
                action="answered_acknowledged",
            )

        elif event_type == "on_hold":
            # Call placed on hold - pause processing
            log.info("Call on hold", call_id=payload.call_id)
            # Could implement pause logic here
            return WebhookResponse(
                success=True,
                action="hold_acknowledged",
            )

        elif event_type == "resumed":
            # Call resumed from hold - resume processing
            log.info("Call resumed", call_id=payload.call_id)
            # Could implement resume logic here
            return WebhookResponse(
                success=True,
                action="resumed_acknowledged",
            )

        elif event_type == "dtmf":
            # DTMF digit received
            digit = payload.data.get("digit", "")
            log.info("DTMF received", call_id=payload.call_id, digit=digit)

            # Handle DTMF menu navigation
            dtmf_response = await _handle_dtmf(service, payload.call_id, digit)
            return WebhookResponse(
                success=True,
                action="dtmf_processed",
                message=dtmf_response,
            )

        elif event_type == "recording_started":
            # Recording started
            recording_id = payload.data.get("recording_id", "")
            log.info(
                "Recording started",
                call_id=payload.call_id,
                recording_id=recording_id,
            )
            return WebhookResponse(
                success=True,
                action="recording_started_acknowledged",
            )

        elif event_type == "recording_stopped":
            # Recording stopped
            recording_id = payload.data.get("recording_id", "")
            recording_url = payload.data.get("url", "")
            log.info(
                "Recording stopped",
                call_id=payload.call_id,
                recording_id=recording_id,
                url=recording_url,
            )
            # Could trigger transcription or archival here
            return WebhookResponse(
                success=True,
                action="recording_stopped_acknowledged",
            )

        else:
            # Unknown event type - log and acknowledge
            log.warning(
                "Unknown event type",
                call_id=payload.call_id,
                event_type=payload.event,
            )
            return WebhookResponse(
                success=True,
                action="acknowledged",
                message=f"Unknown event type: {payload.event}",
            )

    except Exception as e:
        log.error(
            "Event processing failed",
            call_id=payload.call_id,
            event_type=payload.event,
            error=str(e),
        )
        return WebhookResponse(
            success=False,
            message=str(e),
        )


async def _handle_dtmf(service, call_id: str, digit: str) -> str:
    """Handle DTMF digit input.

    Common DTMF menu options:
    - 0: Operator/transfer request
    - 1: Repeat last message
    - 2: Confirm selection
    - *: Cancel/go back
    - #: End input

    Args:
        service: Telephony service instance
        call_id: Call ID
        digit: DTMF digit pressed

    Returns:
        Response message for the action taken
    """
    if digit == "0":
        # Transfer to human operator
        log.info("DTMF: Transfer requested", call_id=call_id)
        return "Transfer to operator requested"

    elif digit == "1":
        # Repeat last message
        log.info("DTMF: Repeat requested", call_id=call_id)
        return "Repeating last message"

    elif digit == "2":
        # Confirm current selection
        log.info("DTMF: Confirmation", call_id=call_id)
        return "Selection confirmed"

    elif digit == "*":
        # Cancel/go back
        log.info("DTMF: Cancel", call_id=call_id)
        return "Cancelled"

    elif digit == "#":
        # End input sequence
        log.info("DTMF: End input", call_id=call_id)
        return "Input ended"

    elif digit in "123456789":
        # Menu selection
        log.info("DTMF: Menu selection", call_id=call_id, option=digit)
        return f"Menu option {digit} selected"

    else:
        return f"Digit {digit} received"


@router.post("/webhooks/call/audio")
async def handle_audio_webhook(
    request: Request,
    payload: AudioWebhook,
    _: None = Depends(validate_generic_webhook),
) -> WebhookResponse:
    """Handle audio data webhook.

    Requires valid HMAC signature in X-Signature header.

    For providers that send audio via HTTP instead of streaming.
    Decodes audio and processes through AI pipeline.
    """
    import base64
    import numpy as np

    log.debug("Audio webhook", call_id=payload.call_id)

    try:
        # Decode audio
        audio_bytes = base64.b64decode(payload.audio_base64)

        # Convert to numpy array
        audio = np.frombuffer(audio_bytes, dtype=np.int16)
        audio = audio.astype(np.float32) / 32768.0

        # Process through AI
        service = get_telephony_service()
        if service.call_handler.is_in_call and service.call_handler.current_call:
            response_text, response_audio = await service.conversation_engine.process_audio(
                audio,
                service.call_handler.current_call.conversation.id,
            )

            # Return audio response as base64
            response_audio_b64 = base64.b64encode(response_audio).decode()

            return WebhookResponse(
                success=True,
                action="audio_response",
                message=response_text[:100],
            )

        return WebhookResponse(success=False, message="No active call")

    except Exception as e:
        log.error("Audio webhook failed", error=str(e))
        return WebhookResponse(success=False, message=str(e))


# Provider-specific endpoints

@router.post("/webhooks/twilio/voice")
async def handle_twilio_voice(request: Request) -> Response:
    """Handle Twilio voice webhook.

    Returns TwiML response for call handling with Media Streams.
    Validates Twilio signature for security.
    """
    # Validate Twilio signature
    try:
        security = get_security_manager()
        await security.validate_twilio(request)
    except WebhookSecurityError as e:
        log.warning(f"Invalid Twilio signature: {e}")
        raise HTTPException(status_code=403, detail="Invalid signature")

    form_data = await request.form()

    call_sid = form_data.get("CallSid", "")
    caller = form_data.get("From", "")
    called = form_data.get("To", "")
    call_status = form_data.get("CallStatus", "")

    log.info(
        "Twilio voice webhook",
        call_sid=call_sid,
        caller=caller,
        called=called,
        status=call_status,
    )

    # Get the base URL for WebSocket
    host = request.headers.get("host", request.base_url.hostname)

    # Register call with telephony service
    service = get_telephony_service()
    await service.handle_webhook_incoming(
        call_id=call_sid,
        caller_id=caller,
        callee_id=called,
        metadata={"provider": "twilio", "status": call_status},
    )

    # Return TwiML to connect to our Media Streams WebSocket
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say language="de-DE">Willkommen. Ich verbinde Sie mit unserem KI-Assistenten.</Say>
    <Connect>
        <Stream url="wss://{host}/api/v1/webhooks/twilio/media/{call_sid}">
            <Parameter name="call_sid" value="{call_sid}" />
            <Parameter name="caller" value="{caller}" />
        </Stream>
    </Connect>
</Response>"""

    return Response(content=twiml, media_type="application/xml")


@router.post("/webhooks/twilio/status")
async def handle_twilio_status(request: Request) -> Response:
    """Handle Twilio status callback webhook.

    Called when call status changes (ringing, in-progress, completed, etc.)
    """
    try:
        security = get_security_manager()
        await security.validate_twilio(request)
    except WebhookSecurityError:
        raise HTTPException(status_code=403, detail="Invalid signature")

    form_data = await request.form()

    call_sid = form_data.get("CallSid", "")
    call_status = form_data.get("CallStatus", "")
    duration = form_data.get("CallDuration", "0")

    log.info(
        "Twilio status webhook",
        call_sid=call_sid,
        status=call_status,
        duration=duration,
    )

    # Handle completed/failed calls
    if call_status in ("completed", "failed", "busy", "no-answer", "canceled"):
        service = get_telephony_service()
        await service.handle_webhook_hangup(call_sid)

    return Response(content="OK", media_type="text/plain")


@router.post("/webhooks/sipgate/incoming")
async def handle_sipgate_incoming(request: Request) -> dict[str, Any]:
    """Handle sipgate incoming call webhook.

    sipgate sends this when a new call arrives.
    Validates sipgate signature for security.
    """
    # Validate sipgate signature
    try:
        security = get_security_manager()
        await security.validate_sipgate(request)
    except WebhookSecurityError as e:
        log.warning(f"Invalid sipgate signature: {e}")
        raise HTTPException(status_code=403, detail="Invalid signature")

    data = await request.json()

    event = data.get("event", "newCall")
    call_id = data.get("callId", "")
    caller = data.get("from", "")
    callee = data.get("to", "")
    direction = data.get("direction", "in")
    user = data.get("user", [])

    log.info(
        "sipgate incoming webhook",
        call_id=call_id,
        caller=caller,
        callee=callee,
        direction=direction,
    )

    # Handle incoming call
    service = get_telephony_service()
    result = await service.handle_webhook_incoming(
        call_id=call_id,
        caller_id=caller,
        callee_id=callee,
        metadata={
            "provider": "sipgate",
            "direction": direction,
            "user": user,
        },
    )

    # Get host for WebSocket URL
    host = request.headers.get("host", "your-server")

    return {
        "action": "accept",
        "audio_stream": f"wss://{host}/api/v1/webhooks/sipgate/audio/{call_id}",
        "internal_call_id": result.get("internal_call_id"),
    }


@router.post("/webhooks/sipgate/hangup")
async def handle_sipgate_hangup(request: Request) -> dict[str, Any]:
    """Handle sipgate hangup webhook."""
    try:
        security = get_security_manager()
        await security.validate_sipgate(request)
    except WebhookSecurityError:
        raise HTTPException(status_code=403, detail="Invalid signature")

    data = await request.json()

    call_id = data.get("callId", "")
    cause = data.get("cause", "normalClearing")
    duration = data.get("duration", 0)

    log.info(
        "sipgate hangup webhook",
        call_id=call_id,
        cause=cause,
        duration=duration,
    )

    service = get_telephony_service()
    await service.handle_webhook_hangup(call_id)

    return {"status": "ok"}


@router.post("/webhooks/sipgate/answer")
async def handle_sipgate_answer(request: Request) -> dict[str, Any]:
    """Handle sipgate answer webhook (call was answered)."""
    try:
        security = get_security_manager()
        await security.validate_sipgate(request)
    except WebhookSecurityError:
        raise HTTPException(status_code=403, detail="Invalid signature")

    data = await request.json()

    call_id = data.get("callId", "")
    answered_number = data.get("answeredNumber", "")

    log.info(
        "sipgate answer webhook",
        call_id=call_id,
        answered_number=answered_number,
    )

    return {"status": "ok"}


# WebSocket endpoints for audio streaming

from fastapi import WebSocket, WebSocketDisconnect
import numpy as np


async def _verify_call_sid(call_sid: str) -> bool:
    """Verify that a call_sid is valid and active.

    Args:
        call_sid: The Twilio call SID to verify

    Returns:
        True if the call is valid/active, False otherwise
    """
    # Basic format validation for Twilio Call SIDs
    # They start with 'CA' and are 34 characters long
    if not call_sid or len(call_sid) < 10:
        return False

    # Check with telephony service if call is tracked
    try:
        service = get_telephony_service()
        # If telephony service is tracking this call, it's valid
        return service.call_handler.is_in_call or call_sid.startswith("CA")
    except Exception:
        # Allow connection if we can't verify (graceful degradation)
        return True


@router.websocket("/webhooks/twilio/media/{call_sid}")
async def twilio_media_stream(websocket: WebSocket, call_sid: str):
    """Twilio Media Streams WebSocket endpoint.

    Handles bidirectional audio streaming with Twilio's Media Streams protocol.

    Protocol:
    - connected: Initial connection event
    - start: Stream started with metadata
    - media: Audio chunks (μ-law 8kHz base64 encoded)
    - stop: Stream ended

    Audio format: μ-law (PCMU), 8kHz, mono, base64 encoded
    """
    # Security: Verify call_sid before accepting connection
    if not await _verify_call_sid(call_sid):
        log.warning("WebSocket rejected - invalid call_sid", call_sid=call_sid)
        await websocket.close(code=4001, reason="Invalid call ID")
        return

    await websocket.accept()
    log.info("Twilio Media Stream connected", call_sid=call_sid)

    # Import telephony audio handler
    from phone_agent.telephony.websocket_audio import TwilioMediaStreamHandler

    handler = TwilioMediaStreamHandler()
    service = get_telephony_service()
    stream_sid: str | None = None

    try:
        while True:
            message = await websocket.receive_json()
            event = message.get("event", "")

            if event == "connected":
                log.debug("Twilio stream connected event", call_sid=call_sid)

            elif event == "start":
                stream_sid = message.get("streamSid", "")
                start_data = message.get("start", {})
                log.info(
                    "Twilio stream started",
                    call_sid=call_sid,
                    stream_sid=stream_sid,
                    media_format=start_data.get("mediaFormat", {}),
                )

            elif event == "media":
                if stream_sid:
                    media = message.get("media", {})
                    payload = media.get("payload", "")

                    # Decode μ-law audio
                    mulaw_bytes = base64.b64decode(payload)

                    # Process through AI pipeline
                    # The handler will decode μ-law → PCM → 16kHz → float32
                    from phone_agent.telephony.codecs import MuLawCodec, AudioResampler

                    codec = MuLawCodec()
                    resampler = AudioResampler(8000, 16000)

                    # Decode and resample
                    pcm_8k = codec.decode(mulaw_bytes)
                    pcm_16k = resampler.resample(pcm_8k)
                    audio_float = pcm_16k.astype(np.float32) / 32768.0

                    # Process through AI if call is active
                    if service.call_handler.is_in_call and service.call_handler.current_call:
                        response_text, response_audio = await service.conversation_engine.process_audio(
                            audio_float,
                            service.call_handler.current_call.conversation.id,
                        )

                        if response_audio is not None and len(response_audio) > 0:
                            # Resample and encode response
                            down_resampler = AudioResampler(16000, 8000)
                            response_8k = down_resampler.resample(
                                (response_audio * 32767).astype(np.int16)
                            )
                            response_mulaw = codec.encode(response_8k)

                            # Send back to Twilio
                            await websocket.send_json({
                                "event": "media",
                                "streamSid": stream_sid,
                                "media": {
                                    "payload": base64.b64encode(response_mulaw).decode("utf-8")
                                }
                            })

            elif event == "stop":
                log.info("Twilio stream stopped", call_sid=call_sid)
                break

            elif event == "mark":
                # Twilio mark event (for synchronization)
                mark_name = message.get("mark", {}).get("name", "")
                log.debug("Twilio mark received", mark=mark_name)

    except WebSocketDisconnect:
        log.info("Twilio Media Stream disconnected", call_sid=call_sid)
    except Exception as e:
        log.error("Twilio Media Stream error", call_sid=call_sid, error=str(e))
    finally:
        await service.handle_webhook_hangup(call_sid)


@router.websocket("/webhooks/sipgate/audio/{call_id}")
async def sipgate_audio_stream(websocket: WebSocket, call_id: str):
    """sipgate audio WebSocket endpoint.

    Handles bidirectional audio streaming for sipgate integration.

    Audio format: G.711 A-law (PCMA), 8kHz, mono
    """
    await websocket.accept()
    log.info("sipgate audio stream connected", call_id=call_id)

    from phone_agent.telephony.codecs import ALawCodec, AudioResampler

    codec = ALawCodec()
    up_resampler = AudioResampler(8000, 16000)
    down_resampler = AudioResampler(16000, 8000)
    service = get_telephony_service()

    try:
        while True:
            # Receive binary audio data
            data = await websocket.receive_bytes()

            if not data:
                continue

            # Decode A-law to PCM
            pcm_8k = codec.decode(data)

            # Resample to 16kHz for AI
            pcm_16k = up_resampler.resample(pcm_8k)
            audio_float = pcm_16k.astype(np.float32) / 32768.0

            # Process through AI
            if service.call_handler.is_in_call and service.call_handler.current_call:
                response_text, response_audio = await service.conversation_engine.process_audio(
                    audio_float,
                    service.call_handler.current_call.conversation.id,
                )

                if response_audio is not None and len(response_audio) > 0:
                    # Resample to 8kHz and encode
                    response_8k = down_resampler.resample(
                        (response_audio * 32767).astype(np.int16)
                    )
                    response_alaw = codec.encode(response_8k)

                    # Send back
                    await websocket.send_bytes(response_alaw)

    except WebSocketDisconnect:
        log.info("sipgate audio stream disconnected", call_id=call_id)
    except Exception as e:
        log.error("sipgate audio stream error", call_id=call_id, error=str(e))
    finally:
        await service.handle_webhook_hangup(call_id)


@router.websocket("/ws/audio/{call_id}")
async def generic_audio_websocket(websocket: WebSocket, call_id: str):
    """Generic WebSocket endpoint for bidirectional audio streaming.

    Used for development testing and generic integrations.
    Audio format: 16-bit PCM, 16kHz, mono (raw bytes)
    """
    await websocket.accept()
    log.info("Generic WebSocket audio connected", call_id=call_id)

    service = get_telephony_service()

    try:
        while True:
            # Receive raw PCM audio
            data = await websocket.receive_bytes()

            if not data:
                continue

            # Convert to numpy
            audio = np.frombuffer(data, dtype=np.int16)
            audio = audio.astype(np.float32) / 32768.0

            # Process through AI
            if service.call_handler.is_in_call and service.call_handler.current_call:
                response_text, response_audio = await service.conversation_engine.process_audio(
                    audio,
                    service.call_handler.current_call.conversation.id,
                )

                if response_audio is not None and len(response_audio) > 0:
                    # Send back as raw PCM
                    response_bytes = (response_audio * 32767).astype(np.int16).tobytes()
                    await websocket.send_bytes(response_bytes)

    except WebSocketDisconnect:
        log.info("Generic WebSocket disconnected", call_id=call_id)
    except Exception as e:
        log.error("Generic WebSocket error", call_id=call_id, error=str(e))
    finally:
        await service.handle_webhook_hangup(call_id)
