"""Web Chat WebSocket for Handwerk job intake.

A simple text-based chat interface for customers to request service.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from itf_shared import get_logger

from phone_agent.db import get_db
from phone_agent.db.repositories import ContactRepository, JobRepository
from phone_agent.services.handwerk_service import HandwerkService
from phone_agent.industry.handwerk.prompts import CHAT_SYSTEM_PROMPT
from phone_agent.ai.llm import LanguageModel

log = get_logger(__name__)

router = APIRouter(prefix="/chat", tags=["Chat"])


class MessageType(str, Enum):
    """Chat message types."""

    MESSAGE = "message"  # Chat message
    JOB_CREATED = "job_created"  # Job was created
    JOB_UPDATE = "job_update"  # Job status update
    INFO_REQUEST = "info_request"  # Bot asks for info
    ERROR = "error"  # Error message


class ChatMessage(BaseModel):
    """Chat message model."""

    type: MessageType
    text: str | None = None
    data: dict[str, Any] | None = None


class ChatSession:
    """Manages a chat session."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.messages: list[dict[str, str]] = []
        self.created_at = datetime.now()
        self.customer_name: str | None = None
        self.customer_phone: str | None = None
        self.customer_address: dict[str, Any] | None = None
        self.job_description: str | None = None
        self.trade_category: str | None = None
        self.urgency: str | None = None

        # Initialize conversation with chat system prompt
        self.messages = [{"role": "system", "content": CHAT_SYSTEM_PROMPT}]

    def add_message(self, role: str, content: str):
        """Add message to conversation history."""
        self.messages.append({"role": role, "content": content})

    async def process_message(
        self,
        user_message: str,
        llm: LanguageModel | None = None,
    ) -> str:
        """Process user message and get LLM response.

        Args:
            user_message: User's text message
            llm: LLM instance (optional, uses mock if not provided)

        Returns:
            AI response text
        """
        self.add_message("user", user_message)

        if llm and llm.is_loaded:
            try:
                # Get LLM response using conversation history
                ai_response = await llm.generate_with_history_async(
                    messages=self.messages,
                    max_tokens=150,
                    temperature=0.7,
                )
                ai_response = ai_response.strip()
            except Exception as e:
                log.error("LLM error", session=self.session_id, error=str(e))
                ai_response = "Entschuldigung, es gab einen Fehler. Können Sie das bitte wiederholen?"
        else:
            # Mock response for testing (when LLM not loaded)
            ai_response = f"Ich verstehe. Sie haben gesagt: '{user_message}'. Wie kann ich Ihnen weiter helfen?"

        self.add_message("assistant", ai_response)
        return ai_response

    async def extract_job_info(self, text: str) -> dict[str, Any] | None:
        """Extract job information from text using simple patterns.

        Args:
            text: User message text

        Returns:
            Dict with extracted info or None
        """
        # Simple keyword-based extraction
        text_lower = text.lower()

        # Trade category detection
        trade_keywords = {
            "shk": ["heizung", "sanitär", "wasser", "rohr", "bad", "wc", "warmwasser"],
            "elektro": ["strom", "licht", "elektr", "sicherung", "kabel", "lampe"],
            "schlosser": ["tür", "schloss", "schlüssel", "fenster"],
            "dachdecker": ["dach", "ziegel", "dachrinne"],
            "maler": ["streichen", "farbe", "tapete", "wand"],
            "tischler": ["möbel", "holz", "schrank", "tisch"],
        }

        detected_trade = "allgemein"
        for trade, keywords in trade_keywords.items():
            if any(keyword in text_lower for keyword in keywords):
                detected_trade = trade
                break

        # Urgency detection
        urgency = "normal"
        if any(word in text_lower for word in ["notfall", "sofort", "dringend", "schnell", "eilig"]):
            if "notfall" in text_lower:
                urgency = "notfall"
            else:
                urgency = "dringend"
        elif any(word in text_lower for word in ["zeit", "nächste woche", "nächsten monat"]):
            urgency = "routine"

        return {
            "trade_category": detected_trade,
            "urgency": urgency,
            "description": text,
        }

    def is_ready_for_job_creation(self) -> bool:
        """Check if we have enough info to create a job."""
        return bool(
            self.customer_name
            and self.job_description
            and self.customer_address
            and self.customer_address.get("zip")
            and self.customer_address.get("city")
        )


# Active sessions
_sessions: dict[str, ChatSession] = {}

# Global LLM instance (initialized on first use)
_llm: LanguageModel | None = None


def get_llm() -> LanguageModel:
    """Get or initialize the global LLM instance."""
    global _llm
    if _llm is None:
        log.info("Initializing LLM for chat...")
        _llm = LanguageModel(
            model="llama-3.2-1b-instruct-q4_k_m.gguf",
            model_path="models/llm",
            n_ctx=2048,
            n_threads=4,
            temperature=0.7,
            max_tokens=150,
        )
        try:
            _llm.load()
            log.info("LLM loaded successfully for chat")
        except Exception as e:
            log.warning("LLM not available, chat will use mock responses", error=str(e))
            _llm = None
    return _llm


@router.websocket("/handwerk")
async def chat_handwerk(
    websocket: WebSocket,
    db: AsyncSession = Depends(get_db),
):
    """WebSocket endpoint for Handwerk text chat.

    Protocol:
        Client → Server:
            {"type": "message", "text": "Heizung kaputt!"}
            {"type": "provide_info", "name": "Max", "phone": "+49...", "address": {...}}

        Server → Client:
            {"type": "message", "text": "Verstanden! ..."}
            {"type": "job_created", "data": {"job_number": "JOB-2024-0001", ...}}
            {"type": "info_request", "text": "Bitte geben Sie Ihre Adresse an"}
    """
    await websocket.accept()

    # Initialize repositories and service
    contact_repo = ContactRepository(db)
    job_repo = JobRepository(db)
    handwerk_service = HandwerkService(contact_repo, job_repo)

    # Get LLM instance
    llm = get_llm()

    # Create session
    session_id = str(uuid4())
    session = ChatSession(session_id)
    _sessions[session_id] = session

    log.info("Chat session started", session_id=session_id)

    try:
        # Send welcome message
        await websocket.send_json({
            "type": MessageType.MESSAGE.value,
            "text": "Willkommen! Ich bin Ihr Handwerker-Assistent. Wie kann ich Ihnen helfen?",
            "data": {"session_id": session_id},
        })

        # Main chat loop
        while True:
            # Receive message
            data = await websocket.receive_json()
            message_type = data.get("type")

            if message_type == "message":
                # User sent a message
                user_text = data.get("text", "")
                log.info("User message", session=session_id, text=user_text[:50])

                # Process message with LLM
                ai_response = await session.process_message(user_text, llm=llm)

                # Extract job info if mentioned
                if not session.job_description and len(user_text) > 20:
                    session.job_description = user_text
                    job_info = await session.extract_job_info(user_text)
                    session.trade_category = job_info["trade_category"]
                    session.urgency = job_info["urgency"]

                # Send response
                await websocket.send_json({
                    "type": MessageType.MESSAGE.value,
                    "text": ai_response,
                })

                # If we don't have customer info yet, request it
                if not session.customer_name:
                    await asyncio.sleep(0.5)
                    await websocket.send_json({
                        "type": MessageType.INFO_REQUEST.value,
                        "text": "Um Ihnen zu helfen, benötige ich noch einige Informationen. Wie ist Ihr Name?",
                    })

            elif message_type == "provide_info":
                # User provided contact/address info
                if data.get("name"):
                    session.customer_name = data["name"]
                if data.get("phone"):
                    session.customer_phone = data["phone"]
                if data.get("address"):
                    session.customer_address = data["address"]

                log.info("Customer info received", session=session_id, name=session.customer_name)

                # Check if we can create job now
                if session.is_ready_for_job_creation():
                    # Send confirmation message
                    await websocket.send_json({
                        "type": MessageType.MESSAGE.value,
                        "text": f"Vielen Dank, {session.customer_name}! Ihr Auftrag wird bearbeitet.",
                    })

                    try:
                        # Create job using HandwerkService
                        job_result = await handwerk_service.create_job_from_intake(
                            customer_name=session.customer_name,
                            description=session.job_description or "Neuer Auftrag",
                            trade_category=session.trade_category or "allgemein",
                            urgency=session.urgency or "normal",
                            customer_phone=session.customer_phone,
                            address=session.customer_address,
                            session_id=session_id,
                        )

                        # Commit the transaction
                        await db.commit()

                        # Send job created notification
                        await websocket.send_json({
                            "type": MessageType.JOB_CREATED.value,
                            "data": {
                                "job_number": job_result["job_number"],
                                "job_id": job_result["job_id"],
                                "status": job_result["status"],
                                "trade_category": job_result["trade_category"],
                                "urgency": job_result["urgency"],
                                "message": job_result["message"],
                            },
                        })

                        log.info(
                            "Job created via chat",
                            session=session_id,
                            job_number=job_result["job_number"],
                            customer=session.customer_name,
                        )

                    except Exception as e:
                        # Rollback on error
                        await db.rollback()
                        log.error("Job creation failed", session=session_id, error=str(e))
                        await websocket.send_json({
                            "type": MessageType.ERROR.value,
                            "text": "Entschuldigung, es gab einen Fehler beim Erstellen des Auftrags. Bitte versuchen Sie es erneut.",
                        })
                else:
                    # Request more info
                    if not session.customer_address:
                        await websocket.send_json({
                            "type": MessageType.INFO_REQUEST.value,
                            "text": "Bitte geben Sie Ihre Adresse an (PLZ und Stadt).",
                        })

            else:
                await websocket.send_json({
                    "type": MessageType.ERROR.value,
                    "text": f"Unbekannter Nachrichtentyp: {message_type}",
                })

    except WebSocketDisconnect:
        log.info("Chat session ended", session_id=session_id)
    except Exception as e:
        log.error("Chat error", session_id=session_id, error=str(e))
        try:
            await websocket.send_json({
                "type": MessageType.ERROR.value,
                "text": "Ein Fehler ist aufgetreten. Bitte versuchen Sie es erneut.",
            })
        except:
            pass
    finally:
        # Cleanup
        if session_id in _sessions:
            del _sessions[session_id]
