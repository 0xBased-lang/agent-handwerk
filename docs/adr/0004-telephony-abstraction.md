# ADR 0004: Telephony Abstraction Layer

## Status

Accepted

## Date

2024-12-01

## Context

German SMEs use various telephony setups:
- Traditional ISDN lines (legacy, still common)
- VoIP/SIP trunks (modern, growing)
- Cloud telephony (Twilio, sipgate)
- On-premise PBX (FreeSWITCH, Asterisk)

We needed to support multiple telephony backends without coupling the core AI logic to any specific provider.

### Requirements

1. **Multiple Providers**: Support Twilio, sipgate, generic SIP, FreeSWITCH
2. **Consistent Interface**: Same API regardless of provider
3. **Real-time Audio**: Bidirectional streaming for STT/TTS
4. **Webhook Support**: Handle provider-specific callbacks
5. **Testability**: Mock provider for development/testing

## Decision

We implemented a **multi-backend telephony abstraction** with provider-specific adapters.

### Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Phone Agent Core                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │
│  │     STT     │  │     LLM     │  │     TTS     │     │
│  └─────────────┘  └─────────────┘  └─────────────┘     │
│         ↑                                    ↓          │
│  ┌─────────────────────────────────────────────────┐   │
│  │            Audio Bridge (WebSocket)              │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
                            ↕
┌─────────────────────────────────────────────────────────┐
│               Telephony Abstraction Layer               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │
│  │   Twilio    │  │   sipgate   │  │ FreeSWITCH  │     │
│  │   Adapter   │  │   Adapter   │  │   Adapter   │     │
│  └─────────────┘  └─────────────┘  └─────────────┘     │
└─────────────────────────────────────────────────────────┘
                            ↕
┌─────────────────────────────────────────────────────────┐
│                    External Systems                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │
│  │ Twilio API  │  │sipgate API  │  │ SIP Trunk   │     │
│  └─────────────┘  └─────────────┘  └─────────────┘     │
└─────────────────────────────────────────────────────────┘
```

### Provider Adapters

#### Twilio Adapter
- **Use Case**: Cloud telephony, easy setup
- **Integration**: REST API + TwiML + Media Streams WebSocket
- **Audio**: Real-time bidirectional via `<Stream>` element

#### sipgate Adapter
- **Use Case**: German VoIP provider, popular with SMEs
- **Integration**: REST API + Webhooks
- **Audio**: SIP-based, requires SIP gateway

#### FreeSWITCH Adapter
- **Use Case**: Self-hosted PBX, full control
- **Integration**: Event Socket Library (ESL)
- **Audio**: Direct media handling via mod_shout

### Common Interface

```python
# telephony/base.py
class TelephonyProvider(ABC):
    @abstractmethod
    async def answer_call(self, call_id: str) -> None:
        """Answer an incoming call."""

    @abstractmethod
    async def hangup(self, call_id: str) -> None:
        """End the call."""

    @abstractmethod
    async def play_audio(self, call_id: str, audio: bytes) -> None:
        """Play audio to the caller."""

    @abstractmethod
    async def get_audio_stream(self, call_id: str) -> AsyncIterator[bytes]:
        """Get incoming audio stream."""

    @abstractmethod
    async def transfer(self, call_id: str, destination: str) -> None:
        """Transfer call to another number."""
```

### Webhook Handlers

Each provider has its own webhook endpoint:

```
POST /api/v1/webhooks/twilio/voice      # Twilio voice events
POST /api/v1/webhooks/twilio/status     # Twilio status callbacks
POST /api/v1/webhooks/sipgate/call      # sipgate call events
POST /api/v1/webhooks/sms/twilio/status # Twilio SMS status
```

### Configuration

```yaml
# configs/production.yaml
telephony:
  enabled: true

  # Twilio (cloud)
  twilio:
    enabled: true
    account_sid: "AC..."
    auth_token: "..."
    from_number: "+49..."
    webhook_url: "https://..."

  # sipgate (German VoIP)
  sipgate:
    enabled: false
    username: "..."
    api_token: "..."

  # FreeSWITCH (self-hosted)
  freeswitch:
    enabled: false
    host: "127.0.0.1"
    port: 8021
    password: "..."
```

## Consequences

### Positive

1. **Provider Flexibility**: Easy to switch providers or use multiple
2. **Testing**: Mock provider enables full E2E testing without real calls
3. **German Market Fit**: Native sipgate support for local SMEs
4. **Self-Hosting Option**: FreeSWITCH for privacy-conscious customers
5. **Separation of Concerns**: AI logic independent of telephony

### Negative

1. **Complexity**: Multiple adapters to maintain
2. **Feature Parity**: Not all features available on all providers
3. **Audio Format Differences**: Need format conversion between providers
4. **Webhook Variations**: Each provider has different payload formats

### Trade-offs

- We accept adapter complexity to gain provider flexibility
- Feature differences documented per provider
- Audio standardized to 16kHz mono PCM internally

## Provider Comparison

| Feature | Twilio | sipgate | FreeSWITCH |
|---------|--------|---------|------------|
| Setup Complexity | Low | Medium | High |
| Monthly Cost | ~€30+ | ~€10-20 | €0 (self-hosted) |
| German Numbers | Yes | Yes | Via trunk |
| Real-time Audio | WebSocket | SIP | ESL |
| Recording | Cloud | Cloud | Local |
| SMS Support | Yes | Yes | Via gateway |

## Related Decisions

- [ADR 0001: Local-First Edge Architecture](./0001-local-first-edge-architecture.md)
