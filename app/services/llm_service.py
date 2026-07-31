"""
Thin abstraction over the DeepSeek chat completion API.
Every LLM call in the system goes through here, so:
  - token usage can be metered per-org for billing (your margin model)
  - the provider can be swapped without touching business logic
"""
import time
from dataclasses import dataclass

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings


@dataclass
class LLMResponse:
    text: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_ms: int


class LLMService:
    def __init__(self):
        self.base_url = settings.DEEPSEEK_BASE_URL.rstrip("/")
        self.api_key = settings.DEEPSEEK_API_KEY
        self.model = settings.DEEPSEEK_MODEL

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def _post(self, payload: dict) -> dict:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=60) as client:
            resp = client.post(f"{self.base_url}/v1/chat/completions", json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.4,
        max_tokens: int = 1000,
    ) -> LLMResponse:
        start = time.time()
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        data = self._post(payload)
        latency_ms = int((time.time() - start) * 1000)

        choice_text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})

        return LLMResponse(
            text=choice_text,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
            latency_ms=latency_ms,
        )

    def complete_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        temperature: float = 0.2,
        max_tokens: int = 1000,
    ) -> dict:
        """
        Function-calling variant — takes a full message list (caller
        manages history) and a tool schema list (OpenAI-compatible
        format, same shape DeepSeek's API accepts). Returns
        {"content": str | None, "tool_calls": list | None} — callers
        should check tool_calls first; content may be None when the model
        only wants to call tools this turn.
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        data = self._post(payload)
        message = data["choices"][0]["message"]
        return {"content": message.get("content"), "tool_calls": message.get("tool_calls")}


llm_service = LLMService()
