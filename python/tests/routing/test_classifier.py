from pipilot_runtime.routing import IntentRouter, RouteInput


class StubRouteClassifier:
    def __init__(self, payload: object) -> None:
        self._payload = payload

    def classify(self, route_input: RouteInput) -> object:
        return self._payload


def test_uses_a_valid_classifier_output() -> None:
    router = IntentRouter(
        classifier=StubRouteClassifier(
            {
                "intent": "review",
                "executionClass": "high_frequency",
            },
        ),
    )

    decision = router.decide(RouteInput(userMessage="看看这个改动"))

    assert decision.intent == "review"
    assert decision.execution_class == "high_frequency"


def test_clarifies_when_classifier_returns_invalid_output() -> None:
    router = IntentRouter(classifier=StubRouteClassifier({"intent": "change"}))

    decision = router.decide(RouteInput(userMessage="看看这个改动"))

    assert decision.intent == "ambiguous"
    assert decision.clarification_question is not None
