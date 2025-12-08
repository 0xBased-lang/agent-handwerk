# LLM Chat Integration Guide

## Overview

The web chat now uses **Llama 3.2 (1B)** for intelligent German responses in the Handwerk context.

## How It Works

```
User: "Meine Heizung ist ausgefallen!"
  ↓
LLM (with CHAT_SYSTEM_PROMPT)
  ↓
Response: "Oh je, Ihre Heizung funktioniert nicht? Seit wann besteht das Problem?"
```

## Architecture

| Component | File | Purpose |
|-----------|------|---------|
| **LLM Engine** | `src/phone_agent/ai/llm.py` | Llama 3.2 inference via llama-cpp-python |
| **Chat Prompt** | `src/phone_agent/industry/handwerk/prompts.py` | `CHAT_SYSTEM_PROMPT` - German trade instructions |
| **WebSocket Integration** | `src/phone_agent/api/chat_websocket.py` | `get_llm()` + `process_message()` |

## System Prompt

The LLM is instructed to:

✅ **Respond SHORT** - Max 2-3 sentences (this is chat, not email)
✅ **Stay on topic** - Collect problem details systematically
✅ **Recognize categories** - Heizung=SHK, Strom=Elektro, Tür=Schlosser
✅ **Handle emergencies** - Gas leak → "Rufen Sie 112!"
✅ **Extract information** - Name, phone, address for job creation

## Setup

### Step 1: Download Models

```bash
cd solutions/phone-agent

# Download Llama 3.2 (1B) - ~700MB
python scripts/download_models.py

# Verify models are present
ls -lh models/llm/
# Should see: llama-3.2-1b-instruct-q4_k_m.gguf
```

### Step 2: Test Chat Without LLM (Mock Mode)

If models aren't downloaded, the chat falls back to mock responses:

```bash
# Start server
uvicorn phone_agent.main:app --reload

# Open browser
# http://localhost:8000/static/chat.html

# Type a message - you'll get mock responses like:
# "Ich verstehe. Sie haben gesagt: 'Heizung kaputt'. Wie kann ich Ihnen weiter helfen?"
```

### Step 3: Test Chat With LLM (Real Mode)

After downloading models:

```bash
# Start server (LLM loads automatically on first chat)
uvicorn phone_agent.main:app --reload

# Open chat
# http://localhost:8000/static/chat.html

# Type: "Meine Heizung ist ausgefallen!"
# LLM responds: "Oh je, Ihre Heizung funktioniert nicht? Seit wann besteht das Problem?"
```

## LLM Loading

The LLM is **lazy-loaded** on first chat message:

```python
# First chat connection
→ get_llm() called
→ LLM model loaded (~5 seconds on Raspberry Pi 5)
→ Chat continues with LLM

# Subsequent chats
→ get_llm() returns existing instance
→ Instant responses
```

## Performance

| Environment | Load Time | Response Time |
|-------------|-----------|---------------|
| **Raspberry Pi 5** (4 CPU threads) | ~5s | ~1-2s per message |
| **MacBook Pro M1** | ~2s | ~0.3-0.5s per message |
| **Server (8 cores)** | ~3s | ~0.5-1s per message |

## Conversation Example

```
User: Hallo! Meine Heizung geht nicht mehr.
Bot:  Oh je, Ihre Heizung funktioniert nicht? Seit wann besteht das Problem?

User: Seit heute Morgen. Es wird gar nicht mehr warm.
Bot:  Das klingt dringend! In welchem Raum befindet sich die Heizung?

User: Im Wohnzimmer im Erdgeschoss.
Bot:  Verstanden. Damit ich einen Auftrag anlegen kann, benötige ich noch Ihre Kontaktdaten.
      Wie ist Ihr Name?

User: Max Mustermann
Bot:  Perfekt! Geben Sie mir bitte auch Ihre Telefonnummer und Adresse.

[User provides phone and address via form]

Bot:  Vielen Dank! Ihr Auftrag JOB-2025-0001 wurde erstellt.
      Ein Techniker meldet sich in Kürze bei Ihnen.
```

## Emergency Handling

The LLM detects emergencies automatically:

### Gas Leak

```
User: Ich rieche Gas in der Küche!
Bot:  ⚠️ NOTFALL! Verlassen Sie SOFORT das Gebäude! Rufen Sie 112!
```

### Water Burst

```
User: Wasserrohrbruch! Überall ist Wasser!
Bot:  Drehen Sie bitte sofort den Haupthahn zu! Ich erstelle einen Notfall-Auftrag.
```

## Troubleshooting

### Models Not Found

```
FileNotFoundError: Model not found: models/llm/llama-3.2-1b-instruct-q4_k_m.gguf
```

**Solution**: Run `python scripts/download_models.py`

### LLM Takes Too Long

If response time > 5s on Raspberry Pi:

```python
# Reduce context window in chat_websocket.py
_llm = LanguageModel(
    n_ctx=1024,  # Reduce from 2048
    max_tokens=100,  # Reduce from 150
)
```

### Out of Memory

```
RuntimeError: Failed to allocate memory
```

**Solution**: Ensure Raspberry Pi has enough RAM:

```bash
# Check memory
free -h

# If low, restart the service
sudo systemctl restart phone-agent
```

## Configuration

### Adjust LLM Parameters

Edit `src/phone_agent/api/chat_websocket.py`:

```python
def get_llm() -> LanguageModel:
    _llm = LanguageModel(
        model="llama-3.2-1b-instruct-q4_k_m.gguf",
        n_ctx=2048,        # Context window (tokens)
        n_threads=4,       # CPU threads
        temperature=0.7,   # Creativity (0.0-1.0)
        max_tokens=150,    # Max response length
    )
```

### Adjust System Prompt

Edit `src/phone_agent/industry/handwerk/prompts.py`:

```python
CHAT_SYSTEM_PROMPT = """
[Your custom instructions here]
"""
```

## Next Steps

- ✅ **Option B Complete**: LLM integrated
- 🔲 **Option C**: Create admin dashboard UI
- 🔲 **Option D**: Deploy to Contabo VPS

## API Reference

### LLM Class

```python
from phone_agent.ai.llm import LanguageModel

llm = LanguageModel()
llm.load()

# Generate with conversation history
response = await llm.generate_with_history_async(
    messages=[
        {"role": "system", "content": "Du bist ein Assistent."},
        {"role": "user", "content": "Hallo!"}
    ],
    max_tokens=150,
    temperature=0.7
)
```

### ChatSession

```python
from phone_agent.api.chat_websocket import ChatSession

session = ChatSession(session_id="abc123")
response = await session.process_message(
    user_message="Heizung kaputt",
    llm=llm  # Optional, uses mock if None
)
```
