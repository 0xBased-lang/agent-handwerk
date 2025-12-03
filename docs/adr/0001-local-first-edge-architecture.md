# ADR 0001: Local-First Edge Architecture

## Status

Accepted

## Date

2024-12-01

## Context

German SMEs, particularly healthcare practices, are bound by strict DSGVO (GDPR) requirements regarding patient data processing. Cloud-based AI services pose several challenges:

1. **Data Sovereignty**: Patient data leaving the practice premises raises compliance concerns
2. **Internet Dependency**: Rural practices may have unreliable connectivity
3. **Latency**: Cloud round-trips add 200-500ms to response times
4. **Cost**: Per-API-call pricing scales poorly with high call volumes
5. **Trust**: Healthcare providers are hesitant to send sensitive data to third parties

We needed to decide between:
- **Option A**: Cloud-based AI services (OpenAI, Google, etc.)
- **Option B**: Edge AI on local hardware (Raspberry Pi, Intel NUC)
- **Option C**: Hybrid approach with local fallback

## Decision

We chose **Option B: Edge AI on Raspberry Pi 5**.

All AI inference (Speech-to-Text, Language Model, Text-to-Speech) runs locally on a Raspberry Pi 5 (8GB) at the customer's premises. No patient data leaves the device.

### Hardware Platform

- **Raspberry Pi 5 8GB** (~135€)
  - 4-core ARM Cortex-A76 @ 2.4GHz
  - 8GB LPDDR4X RAM
  - PCIe 2.0 x1 for AI accelerators
  - Sufficient for real-time AI inference

### AI Models (Local)

| Component | Model | Size | Latency |
|-----------|-------|------|---------|
| STT | distil-whisper-large-v3-german | ~750MB | <500ms |
| LLM | Llama 3.2 1B Q4_K_M | ~800MB | <1000ms |
| TTS | Piper thorsten_de | ~30MB | <300ms |

### Memory Budget

```
Operating System:       ~500MB
Python Runtime:         ~200MB
Whisper Model:          ~750MB
Llama Model:            ~800MB
Piper Model:            ~30MB
Application Buffer:     ~500MB
------------------------
Total:                  ~2.8GB (fits in 4GB, comfortable in 8GB)
```

## Consequences

### Positive

1. **DSGVO Compliance**: Zero data leaves the device - simplifies compliance documentation
2. **Zero Internet Dependency**: Works offline, ideal for rural areas
3. **Low Latency**: End-to-end <2s response time
4. **Predictable Cost**: One-time hardware cost (~335€) vs. ongoing API fees
5. **Customer Trust**: "Your data never leaves your practice" is a strong selling point

### Negative

1. **Hardware Management**: Must ship, install, and maintain physical devices
2. **Model Limitations**: Smaller models than cloud alternatives
3. **Update Complexity**: OTA updates needed for model improvements
4. **Power Dependency**: Device must be powered and running during business hours

### Mitigations

- **Remote Management**: Tailscale VPN + Ansible for updates and diagnostics
- **Model Updates**: OTA system for incremental model improvements
- **Monitoring**: Prometheus + Grafana for device health tracking
- **Fallback**: Webhook mode allows cloud telephony (Twilio) while keeping AI local

## Related Decisions

- [ADR 0003: German Language Optimization](./0003-german-language-optimization.md)
- [ADR 0005: DSGVO Compliance Architecture](./0005-dsgvo-compliance-architecture.md)
