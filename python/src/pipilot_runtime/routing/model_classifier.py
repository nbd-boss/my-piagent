"""Model-backed implementation of the routing classifier boundary."""

from __future__ import annotations

import json

from ..model_provider import ModelProvider
from .models import RouteInput

ROUTE_SYSTEM_PROMPT = """You classify one Coding Agent request. Return one JSON object only, with no Markdown.
Allowed intent values: question, inspect, review, change, run, ambiguous.
Use question only for a general conceptual question. Use inspect for questions about the current repository's code.
For question, inspect, review, change, and run: executionClass is required and must be high_frequency or long_task_agent; clarificationQuestion must be omitted.
For ambiguous only: executionClass must be null; clarificationQuestion is required and must be a non-empty, concise question.
Use high_frequency for bounded repository understanding. Use long_task_agent for requested code changes.
Example: {"userMessage":"Explain this repository's authentication flow. Do not modify files."} returns {"intent":"inspect","executionClass":"high_frequency"}.
Do not decide permissions, tool calls, plans, or verification commands."""


class ModelRouteClassifier:
    """Delegates language understanding to a ModelProvider, not to Router rules."""

    def __init__(self, provider: ModelProvider) -> None:
        self._provider = provider

    def classify(self, route_input: RouteInput) -> object | None:
        """Return parsed JSON when the provider responds with a JSON string."""

        payload = self._provider.complete_json(
            system_prompt=ROUTE_SYSTEM_PROMPT,
            user_prompt=route_input.model_dump_json(by_alias=True, exclude_none=True),
        )
        if not isinstance(payload, str):
            return payload

        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return None
