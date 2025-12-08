#!/usr/bin/env python3
"""Test Handwerk (trades) conversation flow with Groq LLM.

Tests the cloud LLM with German prompts and various Handwerk scenarios.

Usage:
    export GROQ_API_KEY=your_key

    # Run all test scenarios
    python scripts/test_handwerk_conversation.py

    # Interactive chat mode
    python scripts/test_handwerk_conversation.py chat

    # Test specific scenario
    python scripts/test_handwerk_conversation.py --scenario emergency
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@dataclass
class TestScenario:
    """A test scenario for Handwerk conversation."""
    name: str
    description: str
    messages: list[str]
    expected_keywords: list[str]
    urgency: str  # routine, urgent, emergency


# Test scenarios in German
SCENARIOS = [
    TestScenario(
        name="emergency_gas",
        description="Gas leak - must trigger emergency response",
        messages=[
            "Hallo, es riecht hier stark nach Gas in der Kuche!",
        ],
        expected_keywords=["112", "Notfall", "verlassen", "Gebäude", "Gasnotdienst", "sofort"],
        urgency="emergency",
    ),
    TestScenario(
        name="emergency_water",
        description="Water pipe burst - urgent response needed",
        messages=[
            "Hilfe! Bei mir ist ein Wasserrohr geplatzt und es spritzt überall Wasser!",
        ],
        expected_keywords=["Hauptwasserhahn", "zudrehen", "sofort", "dringend", "Techniker"],
        urgency="emergency",
    ),
    TestScenario(
        name="urgent_heating",
        description="Heating failure in winter - same day service",
        messages=[
            "Guten Tag, meine Heizung ist ausgefallen und es ist eiskalt in der Wohnung.",
        ],
        expected_keywords=["Termin", "heute", "Techniker", "dringend"],
        urgency="urgent",
    ),
    TestScenario(
        name="routine_maintenance",
        description="Regular heating maintenance - normal scheduling",
        messages=[
            "Ich möchte einen Termin für die jährliche Heizungswartung vereinbaren.",
        ],
        expected_keywords=["Termin", "Wartung", "Zeitfenster", "wann"],
        urgency="routine",
    ),
    TestScenario(
        name="quote_request",
        description="Quote request for new installation",
        messages=[
            "Was würde eine neue Gastherme bei mir kosten? Meine ist 20 Jahre alt.",
        ],
        expected_keywords=["Besichtigung", "Kostenvoranschlag", "Angebot", "Termin"],
        urgency="routine",
    ),
    TestScenario(
        name="multi_turn_booking",
        description="Multi-turn conversation for appointment booking",
        messages=[
            "Hallo, ich habe ein Problem mit meinem Wasserhahn. Er tropft.",
            "Im Bad, im ersten Stock.",
            "Ja, morgen Vormittag wäre perfekt.",
            "Mein Name ist Müller, die Adresse ist Hauptstraße 15 in Berlin.",
        ],
        expected_keywords=["Termin", "Vormittag", "bestätigt", "Techniker"],
        urgency="urgent",
    ),
]

# Synonym groups for flexible keyword matching
# LLM may use different words with the same meaning
KEYWORD_SYNONYMS = {
    "hauptwasserhahn": ["hauptwasserhahn", "wasserhahn", "absperrventil", "wasser abstellen", "wasser abdrehen", "wasser zudrehen"],
    "zudrehen": ["zudrehen", "abdrehen", "schließen", "abstellen", "absperren"],
    "techniker": ["techniker", "monteur", "fachmann", "handwerker", "mitarbeiter"],
    "heute": ["heute", "sofort", "umgehend", "schnellstmöglich", "gleich", "noch heute"],
    "dringend": ["dringend", "notfall", "eilig", "sofort", "priorität", "akut"],
    "termin": ["termin", "zeitfenster", "zeit", "vereinbaren", "eingetragen"],
    "bestätigt": ["bestätigt", "bestätigung", "gebucht", "eingetragen", "notiert", "vereinbart"],
    # Quote-related keywords
    "besichtigung": ["besichtigung", "besuch", "vor ort", "vorbeikommen", "anschauen", "begutachtung"],
    "kostenvoranschlag": ["kostenvoranschlag", "kosten", "preis", "aufwand", "schätzung", "kalkulation"],
    "angebot": ["angebot", "offerte", "vorschlag", "unterbreiten", "erstellen"],
}


def check_keyword_with_synonyms(keyword: str, text: str) -> bool:
    """Check if keyword or any of its synonyms is in text."""
    keyword_lower = keyword.lower()
    text_lower = text.lower()

    # Direct match
    if keyword_lower in text_lower:
        return True

    # Check synonyms
    if keyword_lower in KEYWORD_SYNONYMS:
        return any(syn in text_lower for syn in KEYWORD_SYNONYMS[keyword_lower])

    return False


def test_scenario(
    llm,
    scenario: TestScenario,
    system_prompt: str,
    verbose: bool = True,
) -> tuple[bool, list[str]]:
    """Test a single conversation scenario.

    Args:
        llm: Language model instance
        scenario: Test scenario to run
        system_prompt: System prompt for the assistant
        verbose: Print detailed output

    Returns:
        Tuple of (passed, issues)
    """
    print(f"\n{'=' * 60}")
    print(f"SCENARIO: {scenario.name}")
    print(f"Description: {scenario.description}")
    print(f"Expected urgency: {scenario.urgency}")
    print("=" * 60)

    messages = [{"role": "system", "content": system_prompt}]
    issues = []
    all_responses = []

    for i, user_msg in enumerate(scenario.messages):
        print(f"\n[User {i+1}]: {user_msg}")

        messages.append({"role": "user", "content": user_msg})

        start = time.time()
        response = llm.generate_with_history(messages)
        latency = (time.time() - start) * 1000

        print(f"[Assistant]: {response}")
        print(f"(Latency: {latency:.0f}ms)")

        messages.append({"role": "assistant", "content": response})
        all_responses.append(response.lower())

    # Check for expected keywords (with synonym support)
    combined_response = " ".join(all_responses)
    missing_keywords = []
    found_keywords = []

    for keyword in scenario.expected_keywords:
        if check_keyword_with_synonyms(keyword, combined_response):
            found_keywords.append(keyword)
        else:
            missing_keywords.append(keyword)

    # Determine pass/fail
    # At least half of expected keywords should be present
    keyword_ratio = len(found_keywords) / len(scenario.expected_keywords)
    passed = keyword_ratio >= 0.5

    print(f"\n--- Results ---")
    print(f"Found keywords: {found_keywords}")
    if missing_keywords:
        print(f"Missing keywords: {missing_keywords}")
    print(f"Keyword match: {keyword_ratio:.0%}")

    # Additional checks for emergency scenarios
    if scenario.urgency == "emergency":
        emergency_indicators = ["112", "notfall", "sofort", "verlassen", "gefahr"]
        has_emergency_response = any(ind in combined_response for ind in emergency_indicators)
        if not has_emergency_response:
            issues.append("Emergency scenario did not trigger proper emergency response")
            passed = False
        else:
            print("Emergency response: TRIGGERED")

    if passed:
        print(f"\n[PASS] Scenario passed!")
    else:
        if missing_keywords:
            issues.append(f"Missing keywords: {missing_keywords}")
        print(f"\n[FAIL] Scenario failed: {issues}")

    return passed, issues


def run_all_scenarios(api_key: str, verbose: bool = True) -> bool:
    """Run all test scenarios.

    Args:
        api_key: Groq API key
        verbose: Print detailed output

    Returns:
        True if all scenarios passed
    """
    from phone_agent.ai.cloud.groq_client import GroqLanguageModel
    from phone_agent.industry.handwerk.prompts import SYSTEM_PROMPT

    print("\n" + "=" * 60)
    print("HANDWERK CONVERSATION TEST SUITE")
    print("=" * 60)

    # Initialize LLM
    print("\nInitializing Groq LLM...")
    llm = GroqLanguageModel(api_key=api_key, model="llama-3.3-70b-versatile")
    llm.load()
    print("LLM ready.")

    results = {}
    all_passed = True

    for scenario in SCENARIOS:
        passed, issues = test_scenario(llm, scenario, SYSTEM_PROMPT, verbose)
        results[scenario.name] = {"passed": passed, "issues": issues}
        if not passed:
            all_passed = False

    # Print summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed_count = sum(1 for r in results.values() if r["passed"])
    total_count = len(results)

    for name, result in results.items():
        status = "[PASS]" if result["passed"] else "[FAIL]"
        print(f"  {status} {name}")
        if result["issues"]:
            for issue in result["issues"]:
                print(f"         - {issue}")

    print(f"\nTotal: {passed_count}/{total_count} passed")

    if all_passed:
        print("\nAll scenarios passed! LLM is ready for Handwerk conversations.")
    else:
        print("\nSome scenarios failed. Review the output above.")

    return all_passed


def interactive_chat(api_key: str):
    """Run interactive chat mode with Handwerk assistant.

    Args:
        api_key: Groq API key
    """
    from phone_agent.ai.cloud.groq_client import GroqLanguageModel
    from phone_agent.industry.handwerk.prompts import SYSTEM_PROMPT

    print("\n" + "=" * 60)
    print("HANDWERK INTERACTIVE CHAT")
    print("=" * 60)
    print("\nYou are now chatting with the Handwerk phone assistant.")
    print("Speak German! Try scenarios like:")
    print("  - 'Meine Heizung ist kaputt'")
    print("  - 'Es riecht nach Gas'")
    print("  - 'Ich möchte einen Termin vereinbaren'")
    print("\nType 'quit' to exit.\n")

    # Initialize LLM
    print("Initializing Groq LLM...")
    llm = GroqLanguageModel(api_key=api_key, model="llama-3.3-70b-versatile")
    llm.load()
    print("Ready!\n")

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Start with greeting
    greeting = llm.generate(
        "Der Anrufer hat gerade angerufen. Begrüße ihn.",
        system_prompt=SYSTEM_PROMPT,
    )
    print(f"[Assistant]: {greeting}\n")
    messages.append({"role": "assistant", "content": greeting})

    while True:
        try:
            user_input = input("[You]: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\nAuf Wiederhören!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("\nAuf Wiederhören!")
            break

        messages.append({"role": "user", "content": user_input})

        start = time.time()
        response = llm.generate_with_history(messages)
        latency = (time.time() - start) * 1000

        print(f"\n[Assistant]: {response}")
        print(f"({latency:.0f}ms)\n")

        messages.append({"role": "assistant", "content": response})


def main():
    parser = argparse.ArgumentParser(
        description="Test Handwerk conversation flow with Groq LLM"
    )
    parser.add_argument(
        "mode",
        nargs="?",
        choices=["test", "chat"],
        default="test",
        help="Mode: test (run scenarios) or chat (interactive)",
    )
    parser.add_argument(
        "--scenario",
        choices=[s.name for s in SCENARIOS],
        help="Run specific scenario only",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("GROQ_API_KEY"),
        help="Groq API key (or set GROQ_API_KEY)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        default=True,
        help="Verbose output",
    )

    args = parser.parse_args()

    if not args.api_key:
        print("Error: GROQ_API_KEY not set")
        print("\nGet a free API key at: https://console.groq.com/")
        print("Then: export GROQ_API_KEY=your_key")
        sys.exit(1)

    if args.mode == "chat":
        interactive_chat(args.api_key)
    else:
        if args.scenario:
            # Run single scenario
            from phone_agent.ai.cloud.groq_client import GroqLanguageModel
            from phone_agent.industry.handwerk.prompts import SYSTEM_PROMPT

            llm = GroqLanguageModel(api_key=args.api_key, model="llama-3.3-70b-versatile")
            llm.load()

            scenario = next(s for s in SCENARIOS if s.name == args.scenario)
            passed, _ = test_scenario(llm, scenario, SYSTEM_PROMPT, args.verbose)
            sys.exit(0 if passed else 1)
        else:
            # Run all scenarios
            success = run_all_scenarios(args.api_key, args.verbose)
            sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
