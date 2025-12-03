"""Language Model using llama-cpp-python.

Runs Llama 3.2 locally on Raspberry Pi 5 for German conversation.
Supports CPU inference and optional NPU acceleration.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Generator

from itf_shared import get_logger

log = get_logger(__name__)


class LanguageModel:
    """Language Model engine using llama-cpp-python.

    Uses quantized Llama 3.2 models for efficient on-device inference.
    """

    def __init__(
        self,
        model: str = "llama-3.2-1b-instruct-q4_k_m.gguf",
        model_path: str | Path = "models/llm",
        n_ctx: int = 2048,
        n_threads: int = 4,
        n_gpu_layers: int = 0,
        temperature: float = 0.7,
        max_tokens: int = 256,
    ) -> None:
        """Initialize LLM engine.

        Args:
            model: Model filename (GGUF format)
            model_path: Directory containing model files
            n_ctx: Context window size
            n_threads: Number of CPU threads
            n_gpu_layers: Layers to offload to GPU/NPU (0 = CPU only)
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
        """
        self.model_name = model
        self.model_path = Path(model_path)
        self.n_ctx = n_ctx
        self.n_threads = n_threads
        self.n_gpu_layers = n_gpu_layers
        self.temperature = temperature
        self.max_tokens = max_tokens

        self._llm: Any = None
        self._loaded = False

    def load(self) -> None:
        """Load the language model.

        Called lazily on first generation or explicitly for preloading.
        """
        if self._loaded:
            return

        try:
            from llama_cpp import Llama

            model_file = self.model_path / self.model_name
            if not model_file.exists():
                raise FileNotFoundError(f"Model not found: {model_file}")

            log.info(
                "Loading LLM model",
                model=self.model_name,
                n_ctx=self.n_ctx,
                n_threads=self.n_threads,
                n_gpu_layers=self.n_gpu_layers,
            )

            self._llm = Llama(
                model_path=str(model_file),
                n_ctx=self.n_ctx,
                n_threads=self.n_threads,
                n_gpu_layers=self.n_gpu_layers,
                verbose=False,
            )
            self._loaded = True

            log.info("LLM model loaded successfully")

        except ImportError:
            log.error("llama-cpp-python not installed")
            raise
        except Exception as e:
            log.error("Failed to load LLM model", error=str(e))
            raise

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
            "Generating response",
            prompt_length=len(prompt),
            temperature=temp,
            max_tokens=tokens,
        )

        # Generate using chat completion
        response = self._llm.create_chat_completion(
            messages=messages,
            temperature=temp,
            max_tokens=tokens,
        )

        text = response["choices"][0]["message"]["content"]

        log.debug(
            "Generation complete",
            response_length=len(text),
            tokens_used=response.get("usage", {}).get("total_tokens", 0),
        )

        return text

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

        log.debug("Starting streaming generation")

        for chunk in self._llm.create_chat_completion(
            messages=messages,
            temperature=temp,
            max_tokens=tokens,
            stream=True,
        ):
            delta = chunk["choices"][0].get("delta", {})
            if content := delta.get("content"):
                yield content

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
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.generate(prompt, system_prompt, temperature, max_tokens),
        )

    def unload(self) -> None:
        """Unload the model to free memory."""
        if self._llm is not None:
            del self._llm
            self._llm = None
            self._loaded = False
            log.info("LLM model unloaded")

    @property
    def is_loaded(self) -> bool:
        """Check if model is currently loaded."""
        return self._loaded


# Default system prompts for healthcare context
HEALTHCARE_SYSTEM_PROMPT = """Du bist ein freundlicher Telefonassistent für eine Arztpraxis in Deutschland.

Deine Aufgaben:
- Begrüße Anrufer höflich auf Deutsch
- Erfasse Name und Anliegen des Anrufers
- Hilf bei der Terminvereinbarung
- Beantworte einfache Fragen zu Öffnungszeiten
- Leite dringende Notfälle weiter

Wichtig:
- Sprich immer Deutsch
- Sei höflich und professionell
- Bei medizinischen Notfällen: Empfehle 112 anzurufen
- Keine medizinische Beratung geben
- Datenschutz beachten

Antworte kurz und prägnant, da dies ein Telefongespräch ist."""
