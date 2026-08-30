"""DeepSeek Chat Completions provider for structured Runtime decisions."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .configuration import DeepSeekConfiguration

RequestSender = Callable[[Request, float], bytes]


class ModelProviderError(RuntimeError):
    """Raised when a provider cannot return a usable model response."""


class DeepSeekProvider:
    """Calls DeepSeek's OpenAI-compatible Chat Completions API without extra dependencies."""

    def __init__(
        self,
        configuration: DeepSeekConfiguration,
        timeout_seconds: float = 20.0,
        request_sender: RequestSender | None = None,
    ) -> None:
        self._configuration = configuration
        self._timeout_seconds = timeout_seconds
        self._request_sender = request_sender or self._send_request

    def complete_json(self, *, system_prompt: str, user_prompt: str) -> object | None:
        """Return the JSON text selected by the first DeepSeek completion choice."""

        request_body = json.dumps(
            {
                "model": self._configuration.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "response_format": {"type": "json_object"},
                "thinking": {"type": "disabled"},
                "temperature": 0,
                "max_tokens": 512,
            },
        ).encode("utf-8")
        request = Request(
            f"{self._configuration.base_url}/chat/completions",
            data=request_body,
            headers={
                "Authorization": f"Bearer {self._configuration.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            response_bytes = self._request_sender(request, self._timeout_seconds)
        except (HTTPError, URLError, TimeoutError) as error:
            raise ModelProviderError(f"DeepSeek request failed: {error}") from error

        try:
            payload = cast(object, json.loads(response_bytes.decode("utf-8")))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ModelProviderError("DeepSeek returned an invalid JSON response") from error
        return self._read_content(payload)

    @staticmethod
    def _send_request(request: Request, timeout_seconds: float) -> bytes:
        with urlopen(request, timeout=timeout_seconds) as response:
            return response.read()

    @staticmethod
    def _read_content(payload: object) -> str:
        if not isinstance(payload, dict):
            raise ModelProviderError("DeepSeek response must be a JSON object")
        record = cast(dict[str, object], payload)
        choices = record.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ModelProviderError("DeepSeek response does not contain a completion choice")
        first_choice = cast(object, choices[0])
        if not isinstance(first_choice, dict):
            raise ModelProviderError("DeepSeek completion choice must be an object")
        message = cast(dict[str, object], first_choice).get("message")
        if not isinstance(message, dict):
            raise ModelProviderError("DeepSeek completion choice does not contain a message")
        content = cast(dict[str, object], message).get("content")
        if not isinstance(content, str) or not content:
            raise ModelProviderError("DeepSeek completion content must be a non-empty string")
        return content
