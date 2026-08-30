"""Classifier boundary used by the Router to obtain a structured decision."""

from __future__ import annotations

from typing import Protocol

from pydantic import ValidationError

from .models import RouteDecision, RouteInput


class RouteClassifier(Protocol):
    """Produces an untrusted routing payload from a user request."""

    def classify(self, route_input: RouteInput) -> object | None:
        """Return a structured payload or no decision."""


def parse_classifier_decision(payload: object) -> RouteDecision | None:
    """Reject malformed classifier output instead of treating it as executable."""

    try:
        return RouteDecision.model_validate(payload)
    except ValidationError:
        return None
