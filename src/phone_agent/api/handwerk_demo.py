"""Handwerker Demo API - WebSocket-based voice interface.

A streamlined demo endpoint for Handwerker (craftsman) phone agent.
Uses cloud AI directly without telephony infrastructure.

Features:
- Browser microphone capture
- Real-time audio streaming with Deepgram STT
- Groq LLM for German conversation
- ElevenLabs TTS for voice responses
- Handwerker-specific prompts and triage

Usage:
1. Open /demo/handwerk in browser
2. Click microphone button to start
3. Speak in German - AI responds
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
from datetime import datetime
from typing import Any
from uuid import uuid4
from enum import Enum

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from itf_shared import get_logger

from phone_agent.industry.handwerk.prompts import SYSTEM_PROMPT

log = get_logger(__name__)

router = APIRouter(prefix="/demo/handwerk", tags=["Handwerk Demo"])


class MessageRole(str, Enum):
    """Message roles for conversation."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class ConversationMessage(BaseModel):
    """A message in the conversation history."""
    role: MessageRole
    content: str
    timestamp: datetime = datetime.now()


class DemoSession:
    """Manages a single demo session with conversation history."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.messages: list[dict[str, str]] = []
        self.created_at = datetime.now()
        self.stt = None
        self.llm = None
        self.tts = None

    async def initialize(self) -> bool:
        """Initialize AI providers."""
        try:
            from phone_agent.ai.cloud.factory import CloudAIConfig, AIProvider, AIFactory

            config = CloudAIConfig(
                enabled=True,
                provider=AIProvider.CLOUD,
                groq_api_key=os.environ.get("GROQ_API_KEY", ""),
                deepgram_api_key=os.environ.get("DEEPGRAM_API_KEY", ""),
                elevenlabs_api_key=os.environ.get("ELEVENLABS_API_KEY", ""),
            )

            factory = AIFactory(config)
            self.stt, self.llm, self.tts = factory.create_all()

            # Initialize with system prompt
            self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]

            log.info("Demo session initialized", session_id=self.session_id)
            return True

        except Exception as e:
            log.error("Failed to initialize demo session", session_id=self.session_id, error=str(e))
            return False

    async def process_audio(self, audio_bytes: bytes) -> tuple[str, str, bytes | None]:
        """Process audio and return transcript, response, and audio.

        Args:
            audio_bytes: Raw PCM audio bytes

        Returns:
            Tuple of (transcript, response_text, response_audio_bytes)
        """
        if not self.stt or not self.llm:
            return "", "AI nicht initialisiert.", None

        # Convert to float for STT
        import numpy as np
        audio = np.frombuffer(audio_bytes, dtype=np.int16)
        audio_float = audio.astype(np.float32) / 32768.0

        # Transcribe
        try:
            transcript = await self.stt.transcribe_async(audio_float, sample_rate=16000)
            if not transcript or not transcript.strip():
                return "", "", None
        except Exception as e:
            log.error("STT failed", error=str(e))
            return "", "", None

        log.debug("Transcribed", text=transcript[:50])

        # Add user message to history
        self.messages.append({"role": "user", "content": transcript})

        # Generate response
        try:
            response = await self.llm.generate_async(
                prompt=transcript,
                system_prompt=SYSTEM_PROMPT,
            )
            if hasattr(self.llm, 'generate_with_history'):
                # Use history if available
                response = self.llm.generate_with_history(self.messages)
        except Exception as e:
            log.error("LLM failed", error=str(e))
            response = "Entschuldigung, ich konnte Ihre Anfrage nicht verarbeiten."

        log.debug("Generated response", text=response[:50])

        # Add assistant response to history
        self.messages.append({"role": "assistant", "content": response})

        # Synthesize audio
        audio_bytes = None
        if self.tts:
            try:
                audio_bytes = await self.tts.synthesize_async(response, output_format="pcm")
            except Exception as e:
                log.error("TTS failed", error=str(e))

        return transcript, response, audio_bytes


# Active sessions
_sessions: dict[str, DemoSession] = {}


DEMO_HTML = """
<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Handwerker Demo - IT-Friends Phone Agent</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        @keyframes pulse-ring {
            0% { transform: scale(0.8); opacity: 0.8; }
            50% { transform: scale(1.2); opacity: 0.4; }
            100% { transform: scale(0.8); opacity: 0.8; }
        }
        .recording .pulse-ring {
            animation: pulse-ring 1.5s ease-in-out infinite;
        }
        .message-enter {
            animation: slideIn 0.3s ease-out;
        }
        @keyframes slideIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
    </style>
</head>
<body class="bg-gray-100 min-h-screen">
    <div class="max-w-6xl mx-auto p-4 md:p-8">
        <!-- Header -->
        <header class="bg-white rounded-2xl shadow-lg p-6 mb-6">
            <div class="flex items-center justify-between">
                <div class="flex items-center gap-4">
                    <div class="text-4xl">🔧</div>
                    <div>
                        <h1 class="text-2xl font-bold text-gray-800">Handwerker Telefonassistent</h1>
                        <p class="text-gray-500">Demo - IT-Friends Phone Agent</p>
                    </div>
                </div>
                <div id="status" class="px-4 py-2 rounded-full text-sm font-medium bg-gray-200 text-gray-600">
                    ● Getrennt
                </div>
            </div>
        </header>

        <!-- Main Layout -->
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <!-- Left: Voice Interface -->
            <div class="lg:col-span-2 space-y-6">
                <!-- Microphone -->
                <div class="bg-white rounded-2xl shadow-lg p-8">
                    <div class="flex flex-col items-center">
                        <button id="micButton" onclick="toggleRecording()"
                            class="relative w-32 h-32 rounded-full bg-gray-100 hover:bg-gray-200
                                   transition-all duration-200 flex items-center justify-center
                                   focus:outline-none focus:ring-4 focus:ring-blue-300">
                            <div class="pulse-ring absolute inset-0 rounded-full bg-red-400 opacity-0"></div>
                            <span id="micIcon" class="text-5xl">🎤</span>
                        </button>
                        <p id="micStatus" class="mt-4 text-gray-500">Klicken zum Aufnehmen</p>
                    </div>
                </div>

                <!-- Conversation -->
                <div class="bg-white rounded-2xl shadow-lg p-6">
                    <h2 class="text-lg font-semibold text-gray-700 mb-4">Gesprächsverlauf</h2>
                    <div id="conversation" class="h-96 overflow-y-auto space-y-4 p-2">
                        <div class="flex justify-center">
                            <p class="text-gray-400 text-sm italic">Gespräch beginnt sobald Sie sprechen...</p>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Right: Info Panel -->
            <div class="space-y-6">
                <!-- Stats -->
                <div class="bg-white rounded-2xl shadow-lg p-6">
                    <h2 class="text-lg font-semibold text-gray-700 mb-4">Session Info</h2>
                    <div class="space-y-3">
                        <div class="flex justify-between">
                            <span class="text-gray-500">Dauer</span>
                            <span id="duration" class="font-mono">0:00</span>
                        </div>
                        <div class="flex justify-between">
                            <span class="text-gray-500">Nachrichten</span>
                            <span id="messageCount" class="font-mono">0</span>
                        </div>
                        <div class="flex justify-between">
                            <span class="text-gray-500">Latenz</span>
                            <span id="latency" class="font-mono">-- ms</span>
                        </div>
                    </div>
                </div>

                <!-- Quick Actions -->
                <div class="bg-white rounded-2xl shadow-lg p-6">
                    <h2 class="text-lg font-semibold text-gray-700 mb-4">Beispiel-Anfragen</h2>
                    <div class="space-y-2">
                        <button onclick="insertExample('Meine Heizung funktioniert nicht mehr')"
                            class="w-full text-left px-4 py-2 bg-gray-50 rounded-lg hover:bg-gray-100
                                   text-sm text-gray-700 transition">
                            "Heizung funktioniert nicht"
                        </button>
                        <button onclick="insertExample('Ich brauche einen Termin für eine Rohrreparatur')"
                            class="w-full text-left px-4 py-2 bg-gray-50 rounded-lg hover:bg-gray-100
                                   text-sm text-gray-700 transition">
                            "Termin Rohrreparatur"
                        </button>
                        <button onclick="insertExample('Es riecht nach Gas in meiner Wohnung')"
                            class="w-full text-left px-4 py-2 bg-red-50 rounded-lg hover:bg-red-100
                                   text-sm text-red-700 transition border border-red-200">
                            ⚠️ "Es riecht nach Gas"
                        </button>
                    </div>
                </div>

                <!-- Info -->
                <div class="bg-blue-50 rounded-2xl p-6 border border-blue-200">
                    <h3 class="font-semibold text-blue-800 mb-2">💡 Hinweis</h3>
                    <p class="text-sm text-blue-700">
                        Dies ist eine Demo des KI-Telefonassistenten für Handwerksbetriebe.
                        Sprechen Sie auf Deutsch und testen Sie verschiedene Szenarien.
                    </p>
                </div>
            </div>
        </div>
    </div>

    <script>
        let ws = null;
        let mediaStream = null;
        let audioContext = null;
        let processor = null;
        let isRecording = false;
        let startTime = null;
        let durationTimer = null;
        let messageCount = 0;
        let audioQueue = [];
        let isPlaying = false;
        let currentAudioSource = null;
        let currentAudioContext = null;

        // Barge-in: Stop audio when user speaks
        function stopAudioPlayback() {
            audioQueue = [];  // Clear queue
            if (currentAudioSource) {
                try {
                    currentAudioSource.stop();
                } catch (e) {}
                currentAudioSource = null;
            }
            if (currentAudioContext) {
                try {
                    currentAudioContext.close();
                } catch (e) {}
                currentAudioContext = null;
            }
            isPlaying = false;
        }

        const statusEl = document.getElementById('status');
        const micButton = document.getElementById('micButton');
        const micIcon = document.getElementById('micIcon');
        const micStatus = document.getElementById('micStatus');
        const conversationEl = document.getElementById('conversation');

        function setStatus(connected, text) {
            statusEl.className = connected
                ? 'px-4 py-2 rounded-full text-sm font-medium bg-green-100 text-green-700'
                : 'px-4 py-2 rounded-full text-sm font-medium bg-gray-200 text-gray-600';
            statusEl.innerHTML = (connected ? '● ' : '○ ') + text;
        }

        function addMessage(text, isUser) {
            // Remove placeholder if exists
            const placeholder = conversationEl.querySelector('.text-gray-400');
            if (placeholder) placeholder.parentElement.remove();

            const div = document.createElement('div');
            div.className = 'message-enter flex ' + (isUser ? 'justify-end' : 'justify-start');
            div.innerHTML = `
                <div class="max-w-[80%] rounded-2xl px-4 py-3 ${
                    isUser
                        ? 'bg-blue-500 text-white'
                        : 'bg-gray-100 text-gray-800'
                }">
                    <p class="text-xs opacity-70 mb-1">${isUser ? 'Sie' : 'Assistent'}</p>
                    <p>${text}</p>
                </div>
            `;
            conversationEl.appendChild(div);
            conversationEl.scrollTop = conversationEl.scrollHeight;

            messageCount++;
            document.getElementById('messageCount').textContent = messageCount;
        }

        async function toggleRecording() {
            if (isRecording) {
                stopRecording();
            } else {
                await startRecording();
            }
        }

        async function startRecording() {
            try {
                // Get microphone
                mediaStream = await navigator.mediaDevices.getUserMedia({
                    audio: {
                        sampleRate: 16000,
                        channelCount: 1,
                        echoCancellation: true,
                        noiseSuppression: true
                    }
                });

                // Setup audio context
                audioContext = new AudioContext({ sampleRate: 16000 });
                const source = audioContext.createMediaStreamSource(mediaStream);
                processor = audioContext.createScriptProcessor(4096, 1, 1);
                source.connect(processor);
                processor.connect(audioContext.destination);

                // Connect WebSocket
                const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                const wsUrl = protocol + '//' + window.location.host + '/demo/handwerk/ws';
                ws = new WebSocket(wsUrl);

                ws.onopen = () => {
                    setStatus(true, 'Verbunden');
                    isRecording = true;
                    micButton.classList.add('recording', 'bg-red-100');
                    micIcon.textContent = '🔴';
                    micStatus.textContent = 'Aufnahme... Klicken zum Stoppen';
                    startTime = Date.now();
                    durationTimer = setInterval(updateDuration, 1000);
                };

                ws.onmessage = async (event) => {
                    const data = JSON.parse(event.data);

                    if (data.type === 'transcript' && data.text) {
                        addMessage(data.text, true);
                    } else if (data.type === 'response' && data.text) {
                        addMessage(data.text, false);

                        // Update latency
                        if (data.latency_ms) {
                            document.getElementById('latency').textContent = data.latency_ms + ' ms';
                        }
                    } else if (data.type === 'audio' && data.data) {
                        // Queue audio for playback
                        audioQueue.push(data.data);
                        if (!isPlaying) playNextAudio();
                    }
                };

                ws.onclose = () => {
                    stopRecording();
                };

                ws.onerror = (err) => {
                    console.error('WebSocket error:', err);
                    setStatus(false, 'Verbindungsfehler');
                    stopRecording();
                };

                // VAD (Voice Activity Detection) settings
                const SILENCE_THRESHOLD = 0.015;  // RMS threshold for silence detection
                const SILENCE_DURATION_MS = 1200;  // 1.2 seconds of silence before sending
                const MIN_AUDIO_LENGTH = 8000;  // Minimum ~0.5s of audio to send
                const MAX_AUDIO_LENGTH = 160000;  // Maximum ~10s of audio

                let audioBuffer = new Float32Array(0);
                let silenceStartTime = null;
                let isSpeaking = false;

                processor.onaudioprocess = (e) => {
                    if (ws && ws.readyState === WebSocket.OPEN) {
                        const inputData = e.inputBuffer.getChannelData(0);

                        // Calculate RMS energy for VAD
                        let sum = 0;
                        for (let i = 0; i < inputData.length; i++) {
                            sum += inputData[i] * inputData[i];
                        }
                        const rms = Math.sqrt(sum / inputData.length);

                        // Accumulate audio
                        const newBuffer = new Float32Array(audioBuffer.length + inputData.length);
                        newBuffer.set(audioBuffer);
                        newBuffer.set(inputData, audioBuffer.length);
                        audioBuffer = newBuffer;

                        // Voice Activity Detection
                        if (rms > SILENCE_THRESHOLD) {
                            // Speech detected - BARGE-IN: stop any playing audio
                            if (isPlaying) {
                                stopAudioPlayback();
                                console.log('Barge-in: Audio stopped');
                            }
                            silenceStartTime = null;
                            if (!isSpeaking) {
                                isSpeaking = true;
                                micStatus.textContent = 'Sprechen...';
                                micIcon.textContent = '🔊';
                            }
                        } else {
                            // Silence detected
                            if (silenceStartTime === null) {
                                silenceStartTime = Date.now();
                            }

                            // Check if silence duration exceeded
                            const silenceDuration = Date.now() - silenceStartTime;
                            if (silenceDuration >= SILENCE_DURATION_MS && audioBuffer.length >= MIN_AUDIO_LENGTH) {
                                // Send accumulated audio
                                micStatus.textContent = 'Verarbeiten...';
                                micIcon.textContent = '⏳';

                                const pcmData = new Int16Array(audioBuffer.length);
                                for (let i = 0; i < audioBuffer.length; i++) {
                                    pcmData[i] = Math.max(-32768, Math.min(32767, audioBuffer[i] * 32768));
                                }
                                ws.send(pcmData.buffer);

                                // Reset
                                audioBuffer = new Float32Array(0);
                                silenceStartTime = null;
                                isSpeaking = false;

                                // Reset UI after short delay
                                setTimeout(() => {
                                    if (isRecording) {
                                        micStatus.textContent = 'Zuhören...';
                                        micIcon.textContent = '🎤';
                                    }
                                }, 500);
                            }
                        }

                        // Safety: send if buffer gets too large (10 seconds)
                        if (audioBuffer.length >= MAX_AUDIO_LENGTH) {
                            const pcmData = new Int16Array(audioBuffer.length);
                            for (let i = 0; i < audioBuffer.length; i++) {
                                pcmData[i] = Math.max(-32768, Math.min(32767, audioBuffer[i] * 32768));
                            }
                            ws.send(pcmData.buffer);
                            audioBuffer = new Float32Array(0);
                            silenceStartTime = null;
                        }
                    }
                };

            } catch (err) {
                console.error('Error starting recording:', err);
                alert('Mikrofon-Zugriff nicht möglich: ' + err.message);
            }
        }

        function stopRecording() {
            isRecording = false;

            if (ws) {
                ws.close();
                ws = null;
            }

            if (processor) {
                processor.disconnect();
                processor = null;
            }

            if (audioContext) {
                audioContext.close();
                audioContext = null;
            }

            if (mediaStream) {
                mediaStream.getTracks().forEach(track => track.stop());
                mediaStream = null;
            }

            if (durationTimer) {
                clearInterval(durationTimer);
                durationTimer = null;
            }

            setStatus(false, 'Getrennt');
            micButton.classList.remove('recording', 'bg-red-100');
            micIcon.textContent = '🎤';
            micStatus.textContent = 'Klicken zum Aufnehmen';
        }

        function updateDuration() {
            if (startTime) {
                const elapsed = Math.floor((Date.now() - startTime) / 1000);
                const mins = Math.floor(elapsed / 60);
                const secs = elapsed % 60;
                document.getElementById('duration').textContent =
                    mins + ':' + secs.toString().padStart(2, '0');
            }
        }

        async function playNextAudio() {
            if (audioQueue.length === 0) {
                isPlaying = false;
                currentAudioSource = null;
                currentAudioContext = null;
                return;
            }

            isPlaying = true;
            const base64Audio = audioQueue.shift();

            try {
                const binaryString = atob(base64Audio);
                const bytes = new Uint8Array(binaryString.length);
                for (let i = 0; i < binaryString.length; i++) {
                    bytes[i] = binaryString.charCodeAt(i);
                }

                // Convert PCM to AudioBuffer (assuming 16-bit 22050Hz from ElevenLabs)
                const pcmData = new Int16Array(bytes.buffer);
                const floatData = new Float32Array(pcmData.length);
                for (let i = 0; i < pcmData.length; i++) {
                    floatData[i] = pcmData[i] / 32768;
                }

                const playbackContext = new AudioContext({ sampleRate: 22050 });
                currentAudioContext = playbackContext;  // Save for barge-in
                const audioBuffer = playbackContext.createBuffer(1, floatData.length, 22050);
                audioBuffer.getChannelData(0).set(floatData);

                const source = playbackContext.createBufferSource();
                currentAudioSource = source;  // Save for barge-in
                source.buffer = audioBuffer;
                source.connect(playbackContext.destination);

                source.onended = () => {
                    currentAudioSource = null;
                    currentAudioContext = null;
                    playbackContext.close();
                    playNextAudio();
                };

                source.start();
            } catch (err) {
                console.error('Error playing audio:', err);
                currentAudioSource = null;
                currentAudioContext = null;
                playNextAudio();
            }
        }

        function insertExample(text) {
            // For text-based testing, send the text directly
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({ type: 'text', text: text }));
                addMessage(text, true);
            } else {
                alert('Bitte starten Sie zuerst die Aufnahme.');
            }
        }
    </script>
</body>
</html>
"""


@router.get("", response_class=HTMLResponse)
async def get_demo_page() -> HTMLResponse:
    """Serve the Handwerker demo page."""
    return HTMLResponse(content=DEMO_HTML)


@router.websocket("/ws")
async def handwerk_demo_websocket(websocket: WebSocket):
    """WebSocket endpoint for Handwerker demo.

    Accepts:
    - Binary: Raw 16-bit PCM audio at 16kHz
    - JSON: { type: "text", text: "..." } for text input

    Sends:
    - { type: "transcript", text: "..." } - STT result
    - { type: "response", text: "...", latency_ms: N } - LLM response
    - { type: "audio", data: "base64..." } - TTS audio
    """
    await websocket.accept()
    session_id = str(uuid4())

    log.info("Handwerk demo session started", session_id=session_id)

    # Create and initialize session
    session = DemoSession(session_id)
    if not await session.initialize():
        await websocket.send_json({
            "type": "error",
            "message": "Failed to initialize AI. Check API keys.",
        })
        await websocket.close()
        return

    _sessions[session_id] = session

    await websocket.send_json({
        "type": "connected",
        "session_id": session_id,
    })

    try:
        while True:
            message = await websocket.receive()

            if message.get("type") == "websocket.disconnect":
                break

            start_time = datetime.now()

            # Handle text message (JSON)
            if "text" in message:
                try:
                    data = json.loads(message["text"])
                    if data.get("type") == "text" and data.get("text"):
                        # Process text input directly
                        user_text = data["text"]

                        # Add to history
                        session.messages.append({"role": "user", "content": user_text})

                        # Generate response
                        if hasattr(session.llm, 'generate_with_history'):
                            response = session.llm.generate_with_history(session.messages)
                        else:
                            response = await session.llm.generate_async(
                                prompt=user_text,
                                system_prompt=SYSTEM_PROMPT,
                            )

                        session.messages.append({"role": "assistant", "content": response})

                        latency = int((datetime.now() - start_time).total_seconds() * 1000)

                        await websocket.send_json({
                            "type": "response",
                            "text": response,
                            "latency_ms": latency,
                        })

                        # Generate audio
                        if session.tts:
                            try:
                                audio_bytes = await session.tts.synthesize_async(response, output_format="pcm")
                                if audio_bytes:
                                    await websocket.send_json({
                                        "type": "audio",
                                        "data": base64.b64encode(audio_bytes).decode(),
                                    })
                            except Exception as e:
                                log.error("TTS failed", error=str(e))
                except json.JSONDecodeError:
                    pass

            # Handle binary message (audio)
            elif "bytes" in message:
                audio_bytes = message["bytes"]

                try:
                    transcript, response, audio = await session.process_audio(audio_bytes)

                    if transcript:
                        await websocket.send_json({
                            "type": "transcript",
                            "text": transcript,
                        })

                    if response:
                        latency = int((datetime.now() - start_time).total_seconds() * 1000)
                        await websocket.send_json({
                            "type": "response",
                            "text": response,
                            "latency_ms": latency,
                        })

                    if audio:
                        await websocket.send_json({
                            "type": "audio",
                            "data": base64.b64encode(audio).decode(),
                        })

                except Exception as e:
                    log.error("Audio processing error", error=str(e))

    except WebSocketDisconnect:
        log.info("Handwerk demo session disconnected", session_id=session_id)
    except Exception as e:
        log.error("Handwerk demo session error", session_id=session_id, error=str(e))
    finally:
        if session_id in _sessions:
            del _sessions[session_id]
        log.info("Handwerk demo session ended", session_id=session_id)


@router.get("/sessions")
async def list_demo_sessions() -> dict[str, Any]:
    """List active demo sessions."""
    return {
        "active_sessions": len(_sessions),
        "sessions": [
            {
                "id": sid,
                "created_at": s.created_at.isoformat(),
                "message_count": len(s.messages),
            }
            for sid, s in _sessions.items()
        ],
    }
