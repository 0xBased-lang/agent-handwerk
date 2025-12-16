"""Multilingual prompt loader for Phone Agent.

Loads industry-specific prompts based on detected language.
Falls back to German if translation not available.
"""

from __future__ import annotations

import importlib
from functools import lru_cache
from typing import Any

from itf_shared import get_logger

log = get_logger(__name__)


# Supported languages
SUPPORTED_LANGUAGES = ["de", "tr", "ru"]

# Industry module paths
INDUSTRY_MODULES = {
    "gesundheit": "phone_agent.industry.gesundheit",
    "handwerk": "phone_agent.industry.handwerk",
    "gastro": "phone_agent.industry.gastro",
    "freie_berufe": "phone_agent.industry.freie_berufe",
}


# ==============================================================================
# Shared Utilities (Industry-Agnostic)
# ==============================================================================


async def get_time_of_day() -> str:
    """Get German greeting based on time of day.

    This is an industry-agnostic utility used for greetings across all industries.

    Returns:
        German time-of-day string: "Morgen", "Mittag", "Nachmittag", or "Abend"
    """
    from datetime import datetime

    hour = datetime.now().hour

    if hour < 11:
        return "Morgen"
    elif hour < 14:
        return "Mittag"
    elif hour < 18:
        return "Nachmittag"
    else:
        return "Abend"


# ==============================================================================
# Prompts Loading
# ==============================================================================


@lru_cache(maxsize=32)
def get_prompts_module(industry: str, language: str = "de") -> Any:
    """Load the prompts module for an industry and language.

    Results are cached to avoid repeated importlib calls.

    Args:
        industry: Industry name (gesundheit, handwerk, gastro, freie_berufe)
        language: Language code (de, tr, ru)

    Returns:
        Prompts module with SYSTEM_PROMPT and other constants
    """
    base_module = INDUSTRY_MODULES.get(industry)
    if not base_module:
        log.warning(
            "Unknown industry, falling back to gesundheit",
            requested=industry,
        )
        base_module = INDUSTRY_MODULES["gesundheit"]

    # Try language-specific module first
    if language != "de" and language in SUPPORTED_LANGUAGES:
        try:
            module_path = f"{base_module}.prompts_{language}"
            module = importlib.import_module(module_path)
            log.debug(
                "Loaded language-specific prompts",
                industry=industry,
                language=language,
            )
            return module
        except ImportError:
            log.debug(
                "Language-specific prompts not found, using German",
                industry=industry,
                language=language,
            )

    # Fall back to German (default)
    try:
        module_path = f"{base_module}.prompts"
        module = importlib.import_module(module_path)
        log.debug(
            "Loaded German prompts",
            industry=industry,
        )
        return module
    except ImportError:
        log.exception(
            "Failed to load prompts module",
            industry=industry,
            language=language,
        )
        raise


@lru_cache(maxsize=32)
def get_system_prompt(industry: str, language: str = "de") -> str:
    """Get the system prompt for an industry and language.

    Args:
        industry: Industry name
        language: Language code

    Returns:
        System prompt string
    """
    module = get_prompts_module(industry, language)
    return module.SYSTEM_PROMPT


@lru_cache(maxsize=32)
def get_greeting_prompt(industry: str, language: str = "de") -> str:
    """Get the greeting prompt for an industry and language.

    Args:
        industry: Industry name
        language: Language code

    Returns:
        Greeting prompt string
    """
    module = get_prompts_module(industry, language)
    return getattr(module, "GREETING_PROMPT", "")


@lru_cache(maxsize=32)
def get_triage_prompt(industry: str, language: str = "de") -> str:
    """Get the triage prompt for healthcare.

    Args:
        industry: Industry name
        language: Language code

    Returns:
        Triage prompt string (healthcare only)
    """
    if industry != "gesundheit":
        return ""

    module = get_prompts_module(industry, language)
    return getattr(module, "TRIAGE_PROMPT", "")


@lru_cache(maxsize=32)
def get_farewell_prompt(industry: str, language: str = "de") -> str:
    """Get the farewell prompt for an industry and language.

    Args:
        industry: Industry name
        language: Language code

    Returns:
        Farewell prompt string
    """
    module = get_prompts_module(industry, language)
    return getattr(module, "FAREWELL_PROMPT", "")


class MultilingualPrompts:
    """Convenience class for accessing prompts in multiple languages.

    Example usage:
        prompts = MultilingualPrompts("gesundheit")
        prompts.set_language("tr")
        system = prompts.system_prompt
    """

    def __init__(self, industry: str, language: str = "de"):
        """Initialize with industry and language.

        Args:
            industry: Industry name
            language: Initial language code
        """
        self.industry = industry
        self._language = language
        self._module: Any = None
        self._load_module()

    def _load_module(self) -> None:
        """Load the prompts module for current language."""
        self._module = get_prompts_module(self.industry, self._language)

    @property
    def language(self) -> str:
        """Get current language."""
        return self._language

    def set_language(self, language: str) -> None:
        """Change the language and reload prompts.

        Args:
            language: New language code
        """
        if language != self._language:
            self._language = language
            self._load_module()
            log.debug(
                "Prompts language changed",
                industry=self.industry,
                language=language,
            )

    @property
    def system_prompt(self) -> str:
        """Get the system prompt."""
        return self._module.SYSTEM_PROMPT

    @property
    def greeting_prompt(self) -> str:
        """Get the greeting prompt."""
        return getattr(self._module, "GREETING_PROMPT", "")

    @property
    def triage_prompt(self) -> str:
        """Get the triage prompt (healthcare only)."""
        return getattr(self._module, "TRIAGE_PROMPT", "")

    @property
    def farewell_prompt(self) -> str:
        """Get the farewell prompt."""
        return getattr(self._module, "FAREWELL_PROMPT", "")

    @property
    def appointment_prompt(self) -> str:
        """Get the appointment prompt."""
        return getattr(self._module, "APPOINTMENT_PROMPT", "")

    @property
    def recall_prompt(self) -> str:
        """Get the recall/campaign prompt."""
        return getattr(self._module, "RECALL_PROMPT", "")

    def get_prompt(self, name: str) -> str:
        """Get any prompt by name.

        Args:
            name: Prompt constant name (e.g., "SYSTEM_PROMPT")

        Returns:
            Prompt string or empty string if not found
        """
        return getattr(self._module, name, "")


# ==============================================================================
# Industry Module Loading (for triage, intake, etc.)
# ==============================================================================


@lru_cache(maxsize=16)
def get_industry_module(industry: str) -> Any:
    """Load the main industry module (triage, intake, etc.).

    This returns the industry's main module which contains:
    - perform_triage() or perform_intake() function
    - TriageResult or IntakeResult dataclass
    - Industry-specific enums and helpers

    Args:
        industry: Industry name (gesundheit, handwerk, gastro, freie_berufe)

    Returns:
        Industry module with triage/intake functions

    Raises:
        ImportError: If industry module not found
    """
    base_module = INDUSTRY_MODULES.get(industry)
    if not base_module:
        log.warning(
            "Unknown industry, falling back to gesundheit",
            requested=industry,
        )
        base_module = INDUSTRY_MODULES["gesundheit"]
        industry = "gesundheit"

    # Each industry has a different main module:
    # - gesundheit: triage.py (perform_triage, TriageResult)
    # - handwerk: __init__.py imports perform_triage from workflows.py
    # - gastro: intake.py (perform_intake, IntakeResult) - if exists
    # - freie_berufe: intake.py (perform_intake, IntakeResult) - if exists

    # Try triage module first (most common)
    try:
        module_path = f"{base_module}.triage"
        module = importlib.import_module(module_path)
        # Check if it has the triage function
        if hasattr(module, "perform_triage"):
            log.debug(
                "Loaded industry triage module",
                industry=industry,
                module=module_path,
            )
            return module
        # Otherwise, fall through to try other modules
    except ImportError:
        pass

    # Try intake module
    try:
        module_path = f"{base_module}.intake"
        module = importlib.import_module(module_path)
        if hasattr(module, "perform_intake"):
            log.debug(
                "Loaded industry intake module",
                industry=industry,
                module=module_path,
            )
            return module
    except ImportError:
        pass

    # Fallback to main __init__ module (some industries like handwerk
    # export perform_triage from the main module which imports from workflows)
    try:
        module = importlib.import_module(base_module)
        log.debug(
            "Loaded industry base module",
            industry=industry,
            module=base_module,
        )
        return module
    except ImportError:
        log.exception(
            "Failed to load industry module",
            industry=industry,
        )
        raise


def get_triage_function(industry: str) -> Any:
    """Get the triage/intake function for an industry.

    Args:
        industry: Industry name

    Returns:
        Callable triage function (perform_triage or perform_intake)
    """
    module = get_industry_module(industry)

    # Try different function names
    for func_name in ["perform_triage", "perform_intake", "classify_request"]:
        func = getattr(module, func_name, None)
        if func is not None:
            return func

    log.warning(
        "No triage function found for industry",
        industry=industry,
    )
    return None


def get_triage_result_class(industry: str) -> Any:
    """Get the TriageResult/IntakeResult class for an industry.

    Args:
        industry: Industry name

    Returns:
        Result dataclass (TriageResult, IntakeResult, etc.)
    """
    module = get_industry_module(industry)

    # Try different class names
    for class_name in ["TriageResult", "IntakeResult", "ClassificationResult"]:
        cls = getattr(module, class_name, None)
        if cls is not None:
            return cls

    log.warning(
        "No result class found for industry",
        industry=industry,
    )
    return None


class IndustryAdapter:
    """Unified adapter for industry-specific functionality.

    Provides a consistent interface regardless of the industry module's
    internal structure. Use this for multi-tenant scenarios where the
    industry changes based on tenant configuration.

    Example usage:
        adapter = IndustryAdapter("handwerk", language="de")
        result = adapter.perform_triage(user_text)
        system_prompt = adapter.system_prompt
    """

    def __init__(self, industry: str, language: str = "de"):
        """Initialize adapter for an industry.

        Args:
            industry: Industry name (gesundheit, handwerk, etc.)
            language: Language code for prompts
        """
        self.industry = industry
        self.language = language
        self._prompts = MultilingualPrompts(industry, language)
        self._triage_module = get_industry_module(industry)
        self._triage_func = get_triage_function(industry)
        self._result_class = get_triage_result_class(industry)

    @property
    def system_prompt(self) -> str:
        """Get the system prompt for this industry."""
        return self._prompts.system_prompt

    @property
    def greeting_prompt(self) -> str:
        """Get the greeting prompt."""
        return self._prompts.greeting_prompt

    @property
    def farewell_prompt(self) -> str:
        """Get the farewell prompt."""
        return self._prompts.farewell_prompt

    @property
    def triage_result_class(self) -> Any:
        """Get the TriageResult class for this industry."""
        return self._result_class

    def perform_triage(self, text: str, **kwargs) -> Any:
        """Perform triage/intake on user text.

        Args:
            text: User input text
            **kwargs: Additional arguments for the triage function

        Returns:
            TriageResult or IntakeResult depending on industry
        """
        if self._triage_func is None:
            log.warning(
                "No triage function available",
                industry=self.industry,
            )
            return None

        return self._triage_func(text, **kwargs)

    def set_language(self, language: str) -> None:
        """Change the language for prompts.

        Args:
            language: New language code
        """
        self.language = language
        self._prompts.set_language(language)

    def get_prompt(self, name: str) -> str:
        """Get any prompt by name.

        Args:
            name: Prompt constant name

        Returns:
            Prompt string or empty if not found
        """
        return self._prompts.get_prompt(name)
