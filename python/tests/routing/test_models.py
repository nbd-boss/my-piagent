import pytest
from pydantic import ValidationError

from pipilot_runtime.routing import RouteDecision


def test_rejects_an_ambiguous_route_that_starts_execution() -> None:
    with pytest.raises(ValidationError):
        RouteDecision(
            intent="ambiguous",
            executionClass="high_frequency",
            clarificationQuestion="What should I investigate?",
        )


def test_rejects_an_executable_route_without_an_execution_class() -> None:
    with pytest.raises(ValidationError):
        RouteDecision(intent="inspect", executionClass=None)
