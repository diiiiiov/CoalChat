from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, AsyncIterator

import httpx


RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class ModelServiceError(RuntimeError):
    """Normalized model-provider error safe to expose to application logs."""


@dataclass(frozen=True)
class ModelClientConfig:
    api_url: str
    api_key: str = ""
    api_style: str = "auto"
    default_model: str = "qwen_coalchat"
    timeout_seconds: float = 60.0
    connect_timeout_seconds: float = 10.0
    max_retries: int = 2


class ModelClient:
    def __init__(self, config: ModelClientConfig):
        self.config = config

    def build_payload(
        self,
        prompt: str,
        model: str | None,
        temperature: float,
        stream: bool,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model or self.config.default_model,
            "max_tokens": 1024,
            "temperature": temperature,
            "stream": stream,
        }
        use_chat = self.config.api_style == "chat" or (
            self.config.api_style == "auto"
            and "/chat/completions" in self.config.api_url
        )
        if use_chat:
            payload["messages"] = [{"role": "user", "content": prompt}]
        else:
            payload["prompt"] = prompt
        return payload

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        return headers

    @staticmethod
    def extract_token(payload: dict[str, Any]) -> str:
        choices = payload.get("choices") or []
        if not choices:
            return ""
        choice = choices[0]
        return choice.get("text") or (choice.get("delta") or {}).get("content") or ""

    @staticmethod
    def _retryable(exc: Exception) -> bool:
        if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
            return True
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code in RETRYABLE_STATUS_CODES
        return False

    async def _backoff(self, attempt: int) -> None:
        await asyncio.sleep(min(2**attempt, 4))

    def _timeout(self) -> httpx.Timeout:
        return httpx.Timeout(
            self.config.timeout_seconds,
            connect=self.config.connect_timeout_seconds,
        )

    async def complete(
        self, prompt: str, model: str | None, temperature: float
    ) -> str:
        payload = self.build_payload(prompt, model, temperature, False)
        last_error: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout()) as client:
                    response = await client.post(
                        self.config.api_url,
                        json=payload,
                        headers=self._headers(),
                    )
                    response.raise_for_status()
                    return self.extract_token(response.json())
            except Exception as exc:
                last_error = exc
                if attempt >= self.config.max_retries or not self._retryable(exc):
                    break
                await self._backoff(attempt)
        raise ModelServiceError(f"模型服务调用失败：{type(last_error).__name__}") from last_error

    async def stream(
        self, prompt: str, model: str | None, temperature: float
    ) -> AsyncIterator[str]:
        payload = self.build_payload(prompt, model, temperature, True)
        last_error: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            emitted = False
            try:
                async with httpx.AsyncClient(timeout=self._timeout()) as client:
                    async with client.stream(
                        "POST",
                        self.config.api_url,
                        json=payload,
                        headers=self._headers(),
                    ) as response:
                        response.raise_for_status()
                        async for line in response.aiter_lines():
                            if not line.startswith("data:"):
                                continue
                            data = line[5:].strip()
                            if not data or data == "[DONE]":
                                continue
                            token = self.extract_token(json.loads(data))
                            if token:
                                emitted = True
                                yield token
                return
            except Exception as exc:
                last_error = exc
                # Once a token is emitted, retrying would duplicate the answer.
                if emitted or attempt >= self.config.max_retries or not self._retryable(exc):
                    break
                await self._backoff(attempt)
        raise ModelServiceError(f"模型流式调用失败：{type(last_error).__name__}") from last_error
