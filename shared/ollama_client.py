"""Ollama LLM client for local model inference."""
import asyncio
import httpx
import os
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


def _merge_fields(response: str, thinking: str) -> str:
    """Merge Ollama response and thinking into a single parseable text.

    Normalizes the two possible thinking modes:
    1. Both fields populated: wrap thinking in <think> tags, prepend to response.
       Parsers that strip <think> see response; parsers that search full text
       find content in either field.
    2. Only thinking populated: return thinking as-is (no wrapping) so parsers
       see structured content directly.
    3. Only response populated: return response (standard case).
    """
    r = (response or "").strip()
    t = (thinking or "").strip()
    if not t:
        return r
    if not r:
        return t
    return f"<think>{t}</think>\n{r}"


class OllamaClient:
    """Ollama client supporting both local and cloud API endpoints."""

    def __init__(
        self,
        host: Optional[str] = None,
        model: Optional[str] = None,
        num_ctx: int = 0,
        think: bool = True,
    ):
        self.host = host or os.getenv("OLLAMA_HOST", "https://api.ollama.com")
        self.default_model = model or os.getenv("LLM_MODEL", "ministral-3:3b")
        self.api_key = os.getenv("OLLAMA_API_KEY")
        self.num_ctx = num_ctx  # 0 = use model default
        self.think = think

    def _get_headers(self) -> Dict[str, str]:
        """Return headers with optional Authorization for Ollama Cloud API."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        think: Optional[bool] = None,
    ) -> Dict:
        """
        Send a chat completion request to Ollama.

        Args:
            think: Override instance-level think setting. None = use instance default.

        Returns dict with 'response' text, 'thinking' text, 'merged' text
        (normalized for parsing), 'eval_count' (tokens), 'eval_duration' (ns).
        """
        use_model = model or self.default_model
        use_think = think if think is not None else self.think
        options = {
            "temperature": temperature,
            "num_predict": max_tokens,
        }
        if self.num_ctx > 0:
            options["num_ctx"] = self.num_ctx
        payload = {
            "model": use_model,
            "messages": messages,
            "options": options,
            "think": use_think,
            "stream": False,
        }

        with httpx.Client(timeout=300.0) as client:
            resp = client.post(
                f"{self.host}/api/chat",
                json=payload,
                headers=self._get_headers(),
            )
            resp.raise_for_status()

        data = resp.json()
        msg = data.get("message", {})
        response = msg.get("content", "")
        thinking = msg.get("thinking", "")
        return {
            "response": response,
            "thinking": thinking,
            "merged": _merge_fields(response, thinking),
            "eval_count": data.get("eval_count", 0),
            "eval_duration": data.get("eval_duration", 0),
        }

    async def chat_async(self, *args, **kwargs) -> Dict:
        """Async wrapper -- runs chat() in a thread pool to avoid blocking the event loop."""
        return await asyncio.to_thread(self.chat, *args, **kwargs)

    def is_available(self) -> bool:
        """Check if Ollama is reachable."""
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(
                    f"{self.host}/api/tags",
                    headers=self._get_headers(),
                )
                return resp.status_code == 200
        except Exception:
            return False

    def list_running_models(self) -> List[str]:
        """List models available in Ollama."""
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(
                    f"{self.host}/api/tags",
                    headers=self._get_headers(),
                )
                resp.raise_for_status()
                data = resp.json()
                return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []
