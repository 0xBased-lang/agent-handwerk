"""Web audio API endpoint for browser-based testing.

Provides a WebSocket endpoint for testing the AI phone agent from
a web browser without needing actual phone infrastructure.

Features:
- Browser microphone capture via WebRTC
- Real-time audio streaming to AI pipeline
- TTS audio playback to browser
- Visual feedback (transcripts, AI responses)

Usage:
1. Open the test page in a browser
2. Click "Start Call" to begin
3. Speak into microphone - AI will respond
4. Click "End Call" when done
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import numpy as np
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from itf_shared import get_logger

from phone_agent.telephony.websocket_audio import (
    WebSocketAudioHandler,
    WebSocketMessageType,
)

log = get_logger(__name__)

router = APIRouter(prefix="/audio", tags=["web-audio"])

# Shared audio handler
_audio_handler: WebSocketAudioHandler | None = None


def get_audio_handler() -> WebSocketAudioHandler:
    """Get or create WebSocket audio handler."""
    global _audio_handler
    if _audio_handler is None:
        _audio_handler = WebSocketAudioHandler(
            sample_rate=16000,
            frame_duration_ms=20,
            max_connections=10,
        )
    return _audio_handler


# Test page HTML
TEST_PAGE_HTML = """
<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Phone Agent - Web Audio Test</title>
    <style>
        * { box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }
        .container {
            background: white;
            border-radius: 12px;
            padding: 24px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        h1 { color: #1a1a1a; margin-bottom: 8px; }
        .subtitle { color: #666; margin-bottom: 24px; }
        .status {
            padding: 12px 16px;
            border-radius: 8px;
            margin-bottom: 20px;
            font-weight: 500;
        }
        .status.disconnected { background: #fee2e2; color: #dc2626; }
        .status.connecting { background: #fef3c7; color: #d97706; }
        .status.connected { background: #d1fae5; color: #059669; }
        .controls {
            display: flex;
            gap: 12px;
            margin-bottom: 24px;
        }
        button {
            padding: 12px 24px;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
        }
        button:disabled { opacity: 0.5; cursor: not-allowed; }
        .btn-start { background: #059669; color: white; }
        .btn-start:hover:not(:disabled) { background: #047857; }
        .btn-stop { background: #dc2626; color: white; }
        .btn-stop:hover:not(:disabled) { background: #b91c1c; }
        .conversation {
            height: 400px;
            overflow-y: auto;
            border: 1px solid #e5e5e5;
            border-radius: 8px;
            padding: 16px;
            background: #fafafa;
        }
        .message {
            margin-bottom: 12px;
            padding: 12px 16px;
            border-radius: 12px;
            max-width: 80%;
        }
        .message.user {
            background: #dbeafe;
            margin-left: auto;
        }
        .message.agent {
            background: #f3f4f6;
        }
        .message.system {
            background: #fef3c7;
            text-align: center;
            max-width: 100%;
            font-style: italic;
        }
        .message .sender {
            font-size: 12px;
            color: #666;
            margin-bottom: 4px;
        }
        .visualizer {
            height: 60px;
            background: #1a1a1a;
            border-radius: 8px;
            margin-bottom: 20px;
        }
        .visualizer canvas { width: 100%; height: 100%; }
        .stats {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 12px;
            margin-top: 20px;
        }
        .stat {
            background: #f9fafb;
            padding: 12px;
            border-radius: 8px;
            text-align: center;
        }
        .stat-value { font-size: 24px; font-weight: 600; color: #1a1a1a; }
        .stat-label { font-size: 12px; color: #666; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🤖 Phone Agent Test</h1>
        <p class="subtitle">Test the AI phone agent from your browser</p>

        <div id="status" class="status disconnected">● Disconnected</div>

        <div class="visualizer">
            <canvas id="visualizer"></canvas>
        </div>

        <div class="controls">
            <button id="startBtn" class="btn-start" onclick="startCall()">
                🎤 Start Call
            </button>
            <button id="stopBtn" class="btn-stop" disabled onclick="endCall()">
                📞 End Call
            </button>
        </div>

        <div id="conversation" class="conversation">
            <div class="message system">
                Click "Start Call" to begin testing the phone agent.
            </div>
        </div>

        <div class="stats">
            <div class="stat">
                <div class="stat-value" id="duration">0:00</div>
                <div class="stat-label">Duration</div>
            </div>
            <div class="stat">
                <div class="stat-value" id="latency">--</div>
                <div class="stat-label">Latency (ms)</div>
            </div>
            <div class="stat">
                <div class="stat-value" id="samples">0</div>
                <div class="stat-label">Audio Frames</div>
            </div>
        </div>
    </div>

    <script>
        let ws = null;
        let mediaStream = null;
        let audioContext = null;
        let processor = null;
        let startTime = null;
        let frameCount = 0;
        let durationTimer = null;

        const statusEl = document.getElementById('status');
        const conversationEl = document.getElementById('conversation');
        const startBtn = document.getElementById('startBtn');
        const stopBtn = document.getElementById('stopBtn');

        function setStatus(status, text) {
            statusEl.className = 'status ' + status;
            statusEl.textContent = '● ' + text;
        }

        function addMessage(sender, text, type = 'user') {
            const msg = document.createElement('div');
            msg.className = 'message ' + type;
            msg.innerHTML = '<div class="sender">' + sender + '</div>' + text;
            conversationEl.appendChild(msg);
            conversationEl.scrollTop = conversationEl.scrollHeight;
        }

        async function startCall() {
            try {
                setStatus('connecting', 'Connecting...');
                startBtn.disabled = true;

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

                // Create script processor for audio capture
                processor = audioContext.createScriptProcessor(4096, 1, 1);
                source.connect(processor);
                processor.connect(audioContext.destination);

                // Connect WebSocket
                const wsUrl = 'ws://' + window.location.host + '/api/v1/audio/ws';
                ws = new WebSocket(wsUrl);

                ws.onopen = () => {
                    setStatus('connected', 'Connected');
                    stopBtn.disabled = false;
                    startTime = Date.now();
                    durationTimer = setInterval(updateDuration, 1000);
                    addMessage('System', 'Call started. Speak into your microphone.', 'system');

                    // Start audio stream
                    ws.send(JSON.stringify({ type: 'start' }));
                };

                ws.onmessage = (event) => {
                    const data = JSON.parse(event.data);

                    if (data.type === 'transcript') {
                        addMessage('You', data.text, 'user');
                    } else if (data.type === 'response') {
                        addMessage('Agent', data.text, 'agent');
                    } else if (data.type === 'audio') {
                        // Play audio response
                        playAudioResponse(data.data);
                    } else if (data.type === 'status') {
                        document.getElementById('latency').textContent =
                            Math.round(Date.now() - data.timestamp || 0);
                    }
                };

                ws.onclose = () => {
                    endCall();
                };

                ws.onerror = (err) => {
                    console.error('WebSocket error:', err);
                    setStatus('disconnected', 'Connection error');
                    endCall();
                };

                // Send audio frames
                processor.onaudioprocess = (e) => {
                    if (ws && ws.readyState === WebSocket.OPEN) {
                        const inputData = e.inputBuffer.getChannelData(0);
                        const pcmData = new Int16Array(inputData.length);
                        for (let i = 0; i < inputData.length; i++) {
                            pcmData[i] = Math.max(-32768, Math.min(32767, inputData[i] * 32768));
                        }
                        ws.send(pcmData.buffer);
                        frameCount++;
                        document.getElementById('samples').textContent = frameCount;
                    }
                };

            } catch (err) {
                console.error('Error starting call:', err);
                setStatus('disconnected', 'Failed to start: ' + err.message);
                startBtn.disabled = false;
            }
        }

        function endCall() {
            if (ws) {
                ws.send(JSON.stringify({ type: 'stop' }));
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

            setStatus('disconnected', 'Disconnected');
            startBtn.disabled = false;
            stopBtn.disabled = true;
            addMessage('System', 'Call ended.', 'system');
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

        async function playAudioResponse(base64Audio) {
            try {
                const audioData = atob(base64Audio);
                const arrayBuffer = new ArrayBuffer(audioData.length);
                const view = new Uint8Array(arrayBuffer);
                for (let i = 0; i < audioData.length; i++) {
                    view[i] = audioData.charCodeAt(i);
                }

                // Convert PCM to AudioBuffer
                const pcmData = new Int16Array(arrayBuffer);
                const floatData = new Float32Array(pcmData.length);
                for (let i = 0; i < pcmData.length; i++) {
                    floatData[i] = pcmData[i] / 32768;
                }

                const audioBuffer = audioContext.createBuffer(1, floatData.length, 16000);
                audioBuffer.getChannelData(0).set(floatData);

                const source = audioContext.createBufferSource();
                source.buffer = audioBuffer;
                source.connect(audioContext.destination);
                source.start();
            } catch (err) {
                console.error('Error playing audio:', err);
            }
        }

        // Setup visualizer
        const canvas = document.getElementById('visualizer');
        const ctx = canvas.getContext('2d');
        canvas.width = canvas.offsetWidth;
        canvas.height = canvas.offsetHeight;

        function drawVisualization() {
            ctx.fillStyle = '#1a1a1a';
            ctx.fillRect(0, 0, canvas.width, canvas.height);

            if (processor && audioContext) {
                // Simple waveform visualization
                ctx.strokeStyle = '#059669';
                ctx.lineWidth = 2;
                ctx.beginPath();

                const centerY = canvas.height / 2;
                const amplitude = canvas.height / 3;

                for (let x = 0; x < canvas.width; x++) {
                    const y = centerY + Math.sin(x * 0.05 + Date.now() * 0.01) * amplitude * 0.3;
                    if (x === 0) ctx.moveTo(x, y);
                    else ctx.lineTo(x, y);
                }

                ctx.stroke();
            }

            requestAnimationFrame(drawVisualization);
        }

        drawVisualization();
    </script>
</body>
</html>
"""


@router.get("/test", response_class=HTMLResponse)
async def get_test_page() -> HTMLResponse:
    """Serve the web audio test page.

    Open in browser to test the phone agent without phone hardware.
    """
    return HTMLResponse(content=TEST_PAGE_HTML)


@router.websocket("/ws")
async def web_audio_websocket(websocket: WebSocket):
    """WebSocket endpoint for browser audio streaming.

    Protocol:
    - Connect: Client connects, server sends session info
    - start: Client starts audio stream
    - Binary frames: Raw 16-bit PCM audio at 16kHz
    - stop: Client ends audio stream

    Server sends:
    - transcript: Speech-to-text results
    - response: AI response text
    - audio: Base64-encoded audio response
    """
    await websocket.accept()
    session_id = uuid4()
    log.info(f"Web audio session started: {session_id}")

    # Send session info
    await websocket.send_json({
        "type": WebSocketMessageType.CONNECTED.value,
        "session_id": str(session_id),
        "sample_rate": 16000,
    })

    # Get services
    from phone_agent.telephony.service import TelephonyService
    service = TelephonyService()

    audio_started = False
    frames_received = 0

    try:
        while True:
            message = await websocket.receive()

            if message.get("type") == "websocket.disconnect":
                break

            # Handle text messages (JSON control)
            if "text" in message:
                data = json.loads(message["text"])
                msg_type = data.get("type", "")

                if msg_type == "start":
                    audio_started = True
                    log.debug(f"Audio stream started: {session_id}")

                    # Create a virtual call for this session
                    await service.start_virtual_call(str(session_id))

                elif msg_type == "stop":
                    audio_started = False
                    log.debug(f"Audio stream stopped: {session_id}")
                    break

                elif msg_type == "status":
                    await websocket.send_json({
                        "type": "status",
                        "session_id": str(session_id),
                        "frames_received": frames_received,
                        "timestamp": datetime.now().timestamp() * 1000,
                    })

            # Handle binary messages (audio data)
            elif "bytes" in message and audio_started:
                audio_bytes = message["bytes"]
                frames_received += 1

                # Convert to numpy float32
                audio = np.frombuffer(audio_bytes, dtype=np.int16)
                audio_float = audio.astype(np.float32) / 32768.0

                # Process through AI pipeline
                try:
                    if service.call_handler.is_in_call and service.call_handler.current_call:
                        result = await service.conversation_engine.process_audio(
                            audio_float,
                            service.call_handler.current_call.conversation.id,
                        )

                        if result:
                            response_text, response_audio = result

                            # Send transcript
                            if response_text:
                                await websocket.send_json({
                                    "type": "transcript",
                                    "text": response_text,
                                    "is_final": True,
                                })

                            # Send response text
                            await websocket.send_json({
                                "type": "response",
                                "text": response_text or "",
                            })

                            # Send audio if available
                            if response_audio is not None and len(response_audio) > 0:
                                import base64
                                audio_int16 = (response_audio * 32767).astype(np.int16)
                                audio_b64 = base64.b64encode(audio_int16.tobytes()).decode()
                                await websocket.send_json({
                                    "type": "audio",
                                    "data": audio_b64,
                                })

                except Exception:
                    log.exception("Audio processing error")

    except WebSocketDisconnect:
        log.info(f"Web audio session disconnected: {session_id}")
    except Exception as e:
        log.error(f"Web audio session error: {e}", session_id=str(session_id))
    finally:
        # Cleanup
        await service.end_virtual_call(str(session_id))
        log.info(f"Web audio session ended: {session_id}")


class SessionStats(BaseModel):
    """Web audio session statistics."""

    session_id: str
    duration_seconds: float
    frames_sent: int
    frames_received: int
    bytes_sent: int
    bytes_received: int


@router.get("/sessions")
async def list_sessions() -> dict[str, Any]:
    """List active web audio sessions."""
    handler = get_audio_handler()
    return {
        "active_sessions": handler.active_sessions,
        "session_ids": [str(sid) for sid in handler.session_ids],
    }
