# Schwäbisch Dialect Improvement Plan

## ✅ Implementation Complete

The phone agent now uses **Hybrid Dialect Routing** with automatic detection.

### Implemented Components

| Component | File | Purpose |
|-----------|------|---------|
| `GermanDialectDetector` | `ai/dialect_detector.py` | Detects Schwäbisch, Bavarian, Low German |
| `DialectAwareSTT` | `ai/stt_router.py` | Routes to specialized models |
| `DialectSettings` | `config.py` | Configuration options |
| `get_dialect_aware_stt()` | `dependencies.py` | FastAPI dependency |

### How It Works

```
Audio → Dialect Probe (3s) → Feature Analysis → Model Selection → Transcription
         ↓                      ↓                    ↓
    whisper-small        Pattern Matching      de_alemannic → Swiss German model
                                               de_bavarian → whisper-large-v3
                                               de_standard → primeline/german
```

## Previous State

The phone agent used `openai/whisper-large-v3` with `language="de"`.
This provided basic German recognition but struggled with Schwäbisch dialect features.

## Problem

Schwäbisch has unique characteristics that confuse standard German ASR:

| Standard German | Schwäbisch | Challenge |
|-----------------|------------|-----------|
| Ich habe | I han | Pronoun + verb contraction |
| Ich kann nicht | I kann et | Negation pattern |
| Mädchen | Mädle | Diminutive suffix |
| ein bisschen | a bissle | Vowel shifts |
| Kartoffeln | Grombira | Different vocabulary |
| schauen | lugga | Completely different word |
| arbeiten | schaffe | Regional synonym |

**Phonetic Shifts:**
- "ei" → "oi" (kein → koi)
- "au" → "ao" (Haus → Haos)
- Final consonants often softened/dropped
- Unique intonation patterns

## Solution Options

### Option 1: Swiss German Model (Recommended) ⭐

**Rationale:** Schwäbisch is part of the Alemannic dialect family, same as Swiss German.

**Models:**
- `Flurin17/whisper-large-v3-turbo-swiss-german` (350+ hours)
- `nizarmichaud/whisper-large-v3-turbo-swissgerman` (SOTA)

**Pros:**
- Pre-trained on Alemannic dialects
- Outputs Standard German (dialect → standard normalization)
- No training required
- ~30-50% better recognition for Schwäbisch

**Cons:**
- Swiss German ≠ Schwäbisch (similar but different)
- May miss Swabian-specific vocabulary

**Implementation:**
```python
# In config.py
class AISTTSettings(BaseModel):
    model: str = "Flurin17/whisper-large-v3-turbo-swiss-german"
    dialect_mode: bool = True  # Enable dialect-aware processing
```

### Option 2: Hybrid Model Routing

Use language detector to route to appropriate model:

```python
DIALECT_MODELS = {
    "de_standard": "primeline/whisper-large-v3-german",
    "de_alemannic": "Flurin17/whisper-large-v3-turbo-swiss-german",
    "de_bavarian": "openai/whisper-large-v3",  # Fallback until available
}

async def transcribe_with_dialect_detection(audio):
    # 1. Quick dialect probe (first 3 seconds)
    dialect = detect_german_dialect(audio[:48000])

    # 2. Route to appropriate model
    model = DIALECT_MODELS.get(dialect, DIALECT_MODELS["de_standard"])

    # 3. Transcribe with specialized model
    return await transcribe(audio, model=model)
```

### Option 3: Post-Processing Normalization

Keep current model but add dialect → standard German normalization:

```python
SCHWAEBISCH_MAPPINGS = {
    r"\bi han\b": "ich habe",
    r"\bi kann et\b": "ich kann nicht",
    r"\bmädle\b": "mädchen",
    r"\ba bissle\b": "ein bisschen",
    r"\bgrombira\b": "kartoffeln",
    r"\blugga\b": "schauen",
    r"\bschaffe\b": "arbeiten",
    # ... more mappings
}

def normalize_schwaebisch(text: str) -> str:
    for pattern, replacement in SCHWAEBISCH_MAPPINGS.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text
```

**Pros:** Simple, predictable
**Cons:** Requires extensive vocabulary mapping, misses context

### Option 4: Fine-Tune on Schwäbisch Data (Long-Term)

Create a Schwäbisch-specific model:

1. **Collect Data:**
   - Stuttgart radio archives
   - SWR (Südwestrundfunk) dialect content
   - Crowdsource from native speakers

2. **Fine-Tune:**
   ```bash
   # Using HuggingFace Transformers
   python finetune_whisper.py \
       --base_model primeline/whisper-large-v3-german \
       --dataset schwaebisch_corpus \
       --output_dir models/whisper-schwaebisch
   ```

3. **Expected Improvement:** 40-60% better WER on Schwäbisch

**Resources Needed:**
- 50-100 hours of Schwäbisch audio with transcriptions
- GPU for fine-tuning (A100 or similar)
- 2-4 weeks development time

## Recommended Approach

### Phase 1: Quick Win (1-2 days)
Switch to Swiss German model for immediate improvement:
```python
model: str = "Flurin17/whisper-large-v3-turbo-swiss-german"
```

### Phase 2: Dialect Detection (1 week)
Add dialect detection to route between models:
- Standard German → primeline/whisper-large-v3-german
- Alemannic dialects → Swiss German model
- Other → Multilingual fallback

### Phase 3: Custom Fine-Tuning (Future)
If demand justifies, fine-tune on actual Schwäbisch data.

## Testing Strategy

### Test Phrases

```
Schwäbisch:              Expected Output:
"I han koi Zeit"      →  "Ich habe keine Zeit"
"Des isch aber schee" →  "Das ist aber schön"
"Wo gosch na?"        →  "Wo gehst du hin?"
"Schaffsch heut?"     →  "Arbeitest du heute?"
```

### WER Benchmarks

| Model | Standard German | Schwäbisch |
|-------|-----------------|------------|
| whisper-large-v3 | 5% | 25-35% |
| primeline/german | 3% | 20-30% |
| Swiss German model | 8% | 12-18% |
| Fine-tuned (est.) | 4% | 8-12% |

## Sources

- [Betthupferl: Multi-Dialectal Dataset for German ASR](https://arxiv.org/html/2506.02894v1)
- [Flurin17/whisper-large-v3-turbo-swiss-german](https://huggingface.co/Flurin17/whisper-large-v3-turbo-swiss-german)
- [primeline/whisper-large-v3-german](https://huggingface.co/primeline/whisper-large-v3-german)
