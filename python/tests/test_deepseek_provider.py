from __future__ import annotations

import json
from typing import cast
from urllib.request import Request

from pipilot_runtime.configuration import DeepSeekConfiguration
from pipilot_runtime.deepseek_provider import DeepSeekProvider


def test_sends_a_structured_chat_completion_request() -> None:
    requests: list[tuple[Request, float]] = []

    def send(request: Request, timeout_seconds: float) -> bytes:
        requests.append((request, timeout_seconds))
        return b'{"choices":[{"message":{"content":"{\\"intent\\":\\"inspect\\"}"}}]}'

    provider = DeepSeekProvider(
        DeepSeekConfiguration(
            api_key="test-key",
            model="deepseek-v4-flash",
            base_url="https://api.deepseek.com",
        ),
        request_sender=send,
    )

    result = provider.complete_json(system_prompt="route", user_prompt='{"userMessage":"Explain auth"}')

    assert result == '{"intent":"inspect"}'
    request, timeout_seconds = requests[0]
    assert request.full_url == "https://api.deepseek.com/chat/completions"
    assert request.get_header("Authorization") == "Bearer test-key"
    assert timeout_seconds == 20.0
    assert request.data is not None
    body = json.loads(cast(bytes, request.data).decode("utf-8"))
    assert body["model"] == "deepseek-v4-flash"
    assert body["response_format"] == {"type": "json_object"}
    assert body["thinking"] == {"type": "disabled"}
