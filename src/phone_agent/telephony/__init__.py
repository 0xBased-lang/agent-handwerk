"""Telephony integration for SIP/VoIP calls.

Supports:
- FreeSWITCH via ESL (Event Socket Library)
- Asterisk via AMI (Asterisk Manager Interface)
- Generic SIP webhooks
- Twilio Media Streams
- sipgate (German VoIP)

Components:
- codecs: G.711 (A-law, μ-law), G.722 encoding/decoding
- rtp_config: RTP packet handling and jitter buffering
- websocket_audio: WebSocket audio streaming (browser, Twilio)
- audio_bridge: Bidirectional audio bridge with codec support
"""

from phone_agent.telephony.sip_client import SIPClient, SIPConfig
from phone_agent.telephony.freeswitch import (
    FreeSwitchClient,
    FreeSwitchConfig,
    FreeSwitchCallSession,
    ChannelState,
    HangupCause,
)
from phone_agent.telephony.audio_bridge import (
    AudioBridge,
    AudioBridgeConfig,
    TelephonyAudioBridge,
    BridgeStatistics,
)
from phone_agent.telephony.codecs import (
    CodecType,
    CodecPipeline,
    MuLawCodec,
    ALawCodec,
    G722Codec,
    AudioResampler,
    get_codec,
)
from phone_agent.telephony.rtp_config import (
    RTPPacket,
    RTPHeader,
    RTPPayloadType,
    JitterBuffer,
    JitterBufferConfig,
    RTPSession,
)
from phone_agent.telephony.websocket_audio import (
    WebSocketAudioHandler,
    TwilioMediaStreamHandler,
    AudioFrame,
)

__all__ = [
    # SIP
    "SIPClient",
    "SIPConfig",
    # FreeSWITCH
    "FreeSwitchClient",
    "FreeSwitchConfig",
    "FreeSwitchCallSession",
    "ChannelState",
    "HangupCause",
    # Audio Bridge
    "AudioBridge",
    "AudioBridgeConfig",
    "TelephonyAudioBridge",
    "BridgeStatistics",
    # Codecs
    "CodecType",
    "CodecPipeline",
    "MuLawCodec",
    "ALawCodec",
    "G722Codec",
    "AudioResampler",
    "get_codec",
    # RTP
    "RTPPacket",
    "RTPHeader",
    "RTPPayloadType",
    "JitterBuffer",
    "JitterBufferConfig",
    "RTPSession",
    # WebSocket
    "WebSocketAudioHandler",
    "TwilioMediaStreamHandler",
    "AudioFrame",
]
