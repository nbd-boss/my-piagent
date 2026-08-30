"""Router that validates a classifier decision and handles uncertainty safely."""

from __future__ import annotations

from .classifier import RouteClassifier, parse_classifier_decision
from .models import RouteDecision, RouteInput


class IntentRouter:
    """Does not know whether its classifier is model-backed or test-only."""

    def __init__(self, classifier: RouteClassifier | None = None) -> None:
        self._classifier = classifier

    def decide(self, route_input: RouteInput) -> RouteDecision:
        """Return a route without reading files or granting permissions."""

        if self._classifier is not None:
            classifier_decision = parse_classifier_decision(self._classifier.classify(route_input))
            if classifier_decision is not None:
                return classifier_decision

        return RouteDecision(
            intent="ambiguous",
            executionClass=None,
            clarificationQuestion="你希望我先定位问题，还是修改代码并补测试？",
            reason="The request needs clarification before work starts.",
        )
