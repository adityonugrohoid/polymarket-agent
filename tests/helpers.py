"""Test helpers shared across test files."""
from shared.ollama_client import _merge_fields


def mcr(response="", thinking="", eval_count=0, eval_duration=0):
    """Build a mock Ollama chat return dict with merged field.

    Use instead of raw dicts so mocks match ollama_client.chat() format.
    Short name (mock chat response) for compact test code.
    """
    return {
        "response": response,
        "thinking": thinking,
        "merged": _merge_fields(response, thinking),
        "eval_count": eval_count,
        "eval_duration": eval_duration,
    }
