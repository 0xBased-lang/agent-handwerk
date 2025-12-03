# ADR 0003: German Language Optimization

## Status

Accepted

## Date

2024-12-01

## Context

IT-Friends Phone Agent serves German SMEs exclusively. All interactions are in German:
- Callers speak German (various dialects)
- AI must understand medical/trade/business German terminology
- Responses must sound natural to German ears
- Text must follow German grammar and conventions

Standard multilingual AI models often underperform on German due to:
- Limited German training data compared to English
- Poor handling of compound words (Krankenversicherungskarte)
- Incorrect formal/informal address (Sie vs. Du)
- Dialect variations (Bavarian, Saxon, etc.)

## Decision

We selected **German-optimized models** for all AI components:

### Speech-to-Text (STT)

**Selected**: `distil-whisper-large-v3-german` (~750MB)

| Model | German WER | Size | Speed |
|-------|------------|------|-------|
| whisper-tiny | 15.2% | 39MB | 32x |
| whisper-small | 9.8% | 244MB | 6x |
| whisper-medium | 7.1% | 769MB | 2x |
| **distil-whisper-large-v3-german** | **5.8%** | **750MB** | **4x** |
| whisper-large-v3 | 5.2% | 1.5GB | 1x |

**Rationale**: Best accuracy-to-size ratio, specifically fine-tuned on German speech.

### Language Model (LLM)

**Selected**: `Llama 3.2 1B Instruct Q4_K_M` (~800MB)

| Model | German Quality | Size | RPi5 Speed |
|-------|---------------|------|------------|
| Phi-2 | Poor | 2.7GB | Slow |
| Mistral 7B | Good | 4GB+ | Too large |
| **Llama 3.2 1B** | **Good** | **800MB** | **~800ms** |
| Llama 3.2 3B | Better | 1.8GB | ~2s |

**Rationale**:
- Fits in memory with STT and TTS
- Good German instruction following
- Q4_K_M quantization balances quality and size

### Text-to-Speech (TTS)

**Selected**: `Piper thorsten_de medium` (~30MB)

| Voice | Naturalness | Size | Speed |
|-------|-------------|------|-------|
| espeak-ng German | Robotic | 1MB | Fast |
| Coqui TTS German | Good | 200MB | Slow |
| **Piper thorsten_de** | **Natural** | **30MB** | **Fast** |

**Rationale**:
- Native German voice (Thorsten voice)
- Very small model size
- Fast synthesis (<300ms for typical response)
- Open source, no licensing issues

## Consequences

### Positive

1. **Better Recognition**: 5.8% WER vs. 9.8% for generic models
2. **Natural Output**: German-native TTS sounds professional
3. **Memory Efficient**: All models fit in 3GB total
4. **Low Latency**: End-to-end <2s on Raspberry Pi 5
5. **Offline Capable**: All models run locally

### Negative

1. **German-Only**: System cannot handle other languages
2. **Dialect Challenges**: Some regional accents still problematic
3. **Model Updates**: Must manually update when better models available
4. **Terminology Gaps**: Medical terms may need prompt engineering

### Mitigations

- **Dialect Handling**: Prompt engineering to request standard German
- **Terminology**: Industry-specific word lists in prompts
- **Future Updates**: OTA model update capability built-in

## German-Specific Optimizations

### Formal Address (Sie-Form)

All prompts use formal German "Sie" form:
```python
GREETING_PROMPT = """
Guten Tag, hier ist die Praxis {practice_name}.
Wie kann ich Ihnen helfen?
"""  # Note: "Ihnen" (formal) not "dir" (informal)
```

### Compound Words

System prompt includes instruction to handle compounds:
```python
SYSTEM_PROMPT = """
...
Verstehe zusammengesetzte Wörter wie:
- Krankenversicherungskarte (health insurance card)
- Terminvereinbarung (appointment scheduling)
- Beschwerden (complaints/symptoms)
...
"""
```

### Time and Date Formats

German formats in all outputs:
```python
# Time: 24-hour format
"Ihr Termin ist um 14:30 Uhr"  # Not "2:30 PM"

# Date: DD.MM.YYYY
"Am 15.01.2025"  # Not "01/15/2025" or "January 15"
```

## Performance Measurements

### Raspberry Pi 5 (No Accelerator)

| Component | Model | Latency | Memory |
|-----------|-------|---------|--------|
| STT | distil-whisper-large-v3-de | ~400ms | ~750MB |
| LLM | Llama 3.2 1B Q4_K_M | ~800ms | ~800MB |
| TTS | Piper thorsten_de | ~250ms | ~30MB |
| **Total** | - | **~1.5s** | **~2.8GB** |

### With Hailo-8L Accelerator

| Component | Latency (Accelerated) |
|-----------|-----------------------|
| STT | ~200ms |
| LLM | ~400ms |
| TTS | ~250ms (CPU) |
| **Total** | **~850ms** |

## Related Decisions

- [ADR 0001: Local-First Edge Architecture](./0001-local-first-edge-architecture.md)
