"""Language Model using Groq API.

Cloud LLM provider with ultra-fast inference (~300ms latency).
Implements the same interface as local LanguageModel for seamless switching.
Includes retry logic with exponential backoff for transient failures.
"""

from __future__ import annotations

import asyncio
import time
from typing import Generator

from itf_shared import get_logger

from phone_agent.core.retry import (
    retry_async,
    RetryConfig,
    get_circuit_breaker,
    CircuitOpen,
)

log = get_logger(__name__)

# Groq-specific retry config: 3 attempts, 0.5s base delay
GROQ_RETRY_CONFIG = RetryConfig(
    max_attempts=3,
    base_delay=0.5,
    max_delay=10.0,
    retryable_exceptions=(ConnectionError, TimeoutError, OSError, RuntimeError),
)


class GroqLanguageModel:
    """Language Model engine using Groq API.

    Uses Llama 3.1 models with Groq's LPU for ultra-fast inference.
    Compatible with local LanguageModel interface.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "llama-3.3-70b-versatile",
        temperature: float = 0.7,
        max_tokens: int = 256,
    ) -> None:
        """Initialize Groq LLM client.

        Args:
            api_key: Groq API key
            model: Model name (llama-3.1-70b-versatile, llama-3.1-8b-instant, etc.)
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
        """
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

        self._client = None
        self._loaded = False

        # Circuit breaker for Groq API
        self._circuit_breaker = get_circuit_breaker(
            name="groq_api",
            failure_threshold=5,
            reset_timeout=60.0,
        )

    def load(self) -> None:
        """Initialize the Groq client.

        Called lazily on first generation or explicitly for preloading.
        """
        if self._loaded:
            return

        try:
            from groq import Groq

            log.info(
                "Initializing Groq client",
                model=self.model,
            )

            self._client = Groq(api_key=self.api_key)
            self._loaded = True

            log.info("Groq client initialized successfully")

        except ImportError:
            log.error("groq package not installed. Run: pip install groq")
            raise
        except Exception as e:
            log.error("Failed to initialize Groq client", error=str(e))
            raise

    def _call_api_with_retry(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        stream: bool = False,
    ):
        """Call Groq API with retry and circuit breaker protection.

        Args:
            messages: Chat messages
            temperature: Sampling temperature
            max_tokens: Max tokens to generate
            stream: Whether to stream response

        Returns:
            API response

        Raises:
            CircuitOpen: If circuit breaker is open
            Exception: If all retries exhausted
        """
        # Check circuit breaker
        if not self._circuit_breaker.allow_request():
            reset_at = self._circuit_breaker.reset_at
            log.warning(
                "Groq circuit breaker open",
                reset_at=reset_at.isoformat() if reset_at else None,
            )
            raise CircuitOpen(
                self._circuit_breaker.name,
                reset_at or __import__("datetime").datetime.now(),
            )

        last_error = None
        for attempt in range(1, GROQ_RETRY_CONFIG.max_attempts + 1):
            try:
                start_time = time.time()

                response = self._client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=stream,
                )

                # Success - record it
                self._circuit_breaker.record_success()

                elapsed = time.time() - start_time
                log.debug(f"Groq API call succeeded in {elapsed:.2f}s")

                return response

            except Exception as e:
                last_error = e
                self._circuit_breaker.record_failure()

                if not GROQ_RETRY_CONFIG.should_retry(e, attempt):
                    log.error(
                        "Groq API call failed (non-retryable)",
                        error=str(e),
                        attempt=attempt,
                    )
                    raise

                delay = GROQ_RETRY_CONFIG.calculate_delay(attempt)
                log.warning(
                    f"Groq API call failed, retrying in {delay:.2f}s",
                    error=str(e),
                    attempt=attempt,
                    max_attempts=GROQ_RETRY_CONFIG.max_attempts,
                )

                time.sleep(delay)

        # All retries exhausted
        log.error(
            "Groq API call failed after all retries",
            error=str(last_error),
            attempts=GROQ_RETRY_CONFIG.max_attempts,
        )
        raise last_error or RuntimeError("Groq API call failed")

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Generate text completion.

        Args:
            prompt: User prompt/message
            system_prompt: Optional system prompt for context
            temperature: Override default temperature
            max_tokens: Override default max tokens

        Returns:
            Generated text response
        """
        if not self._loaded:
            self.load()

        temp = temperature if temperature is not None else self.temperature
        tokens = max_tokens if max_tokens is not None else self.max_tokens

        # Build messages for chat format
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        log.debug(
            "Generating response via Groq",
            prompt_length=len(prompt),
            model=self.model,
            temperature=temp,
            max_tokens=tokens,
        )

        # Generate using chat completion with retry
        response = self._call_api_with_retry(
            messages=messages,
            temperature=temp,
            max_tokens=tokens,
        )

        text = response.choices[0].message.content

        log.debug(
            "Groq generation complete",
            response_length=len(text) if text else 0,
            tokens_used=response.usage.total_tokens if response.usage else 0,
        )

        return text or ""

    def generate_stream(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> Generator[str, None, None]:
        """Generate text with streaming output.

        Yields tokens as they are generated for lower latency.

        Args:
            prompt: User prompt/message
            system_prompt: Optional system prompt for context
            temperature: Override default temperature
            max_tokens: Override default max tokens

        Yields:
            Generated text tokens
        """
        if not self._loaded:
            self.load()

        temp = temperature if temperature is not None else self.temperature
        tokens = max_tokens if max_tokens is not None else self.max_tokens

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        log.debug("Starting streaming generation via Groq")

        stream = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temp,
            max_tokens=tokens,
            stream=True,
        )

        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def generate_async(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Async wrapper for generation.

        Runs generation in a thread pool to avoid blocking.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.generate(prompt, system_prompt, temperature, max_tokens),
        )

    def generate_with_history(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Generate response with full conversation history.

        Args:
            messages: List of {"role": "system|user|assistant", "content": "..."}
            temperature: Override default temperature
            max_tokens: Override default max tokens

        Returns:
            Generated text response
        """
        if not self._loaded:
            self.load()

        temp = temperature if temperature is not None else self.temperature
        tokens = max_tokens if max_tokens is not None else self.max_tokens

        log.debug(
            "Generating with history via Groq",
            num_messages=len(messages),
            model=self.model,
            temperature=temp,
            max_tokens=tokens,
        )

        # Use retry-protected API call
        response = self._call_api_with_retry(
            messages=messages,
            temperature=temp,
            max_tokens=tokens,
        )

        text = response.choices[0].message.content

        log.debug(
            "Groq generation complete",
            response_length=len(text) if text else 0,
            tokens_used=response.usage.total_tokens if response.usage else 0,
        )

        return text or ""

    async def generate_with_history_async(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Async wrapper for generate_with_history."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.generate_with_history(messages, temperature, max_tokens),
        )

    def generate_stream_with_history(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> Generator[str, None, None]:
        """Stream generation with full conversation history.

        Args:
            messages: List of {"role": "system|user|assistant", "content": "..."}
            temperature: Override default temperature
            max_tokens: Override default max tokens

        Yields:
            Generated text tokens
        """
        if not self._loaded:
            self.load()

        temp = temperature if temperature is not None else self.temperature
        tokens = max_tokens if max_tokens is not None else self.max_tokens

        log.debug(
            "Starting streaming generation with history via Groq",
            num_messages=len(messages),
        )

        stream = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temp,
            max_tokens=tokens,
            stream=True,
        )

        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def unload(self) -> None:
        """Unload the client to free resources."""
        if self._client is not None:
            self._client = None
            self._loaded = False
            log.info("Groq client unloaded")

    @property
    def is_loaded(self) -> bool:
        """Check if client is currently loaded."""
        return self._loaded


# Default system prompts for Handwerk context
HANDWERK_SYSTEM_PROMPT = """Du bist ein freundlicher Telefonassistent für einen Handwerksbetrieb in Deutschland.

Deine Aufgaben:
- Begrüße Anrufer höflich auf Deutsch
- Erfasse Name, Adresse und Anliegen des Anrufers
- Führe eine Dringlichkeitseinschätzung durch
- Hilf bei der Terminvereinbarung für Serviceeinsätze
- Bei Notfällen (Gas, Wasser, Strom): Sofortige Weiterleitung empfehlen

Wichtig:
- Sprich immer Deutsch
- Sei höflich und professionell
- Halte Antworten kurz (max 2-3 Sätze) - dies ist ein Telefongespräch
- Frage nach wichtigen Details wie Adresse und Telefonnummer
- Bei Gasgeruch oder elektrischen Problemen: 112 empfehlen

Antworte kurz und prägnant."""
