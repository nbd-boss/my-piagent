"""Validated domain models for the intent-routing boundary."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ExecutionClass = Literal["high_frequency", "long_task_agent"]
Intent = Literal["question", "inspect", "change", "review", "run", "ambiguous"]


class CurrentTask(BaseModel):
    """Minimal context available when a user adds a constraint to an active task."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    goal: str = Field(min_length=1)
    execution_class: ExecutionClass = Field(alias="executionClass")


class RouteInput(BaseModel):
    """The smallest input needed to make an initial routing decision."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    user_message: str = Field(alias="userMessage", min_length=1)
    current_task: CurrentTask | None = Field(default=None, alias="currentTask")


class RouteDecision(BaseModel):
    """A safe, minimal decision made before planning or tool use."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    intent: Intent
    execution_class: ExecutionClass | None = Field(alias="executionClass")
    clarification_question: str | None = Field(default=None, alias="clarificationQuestion")
    reason: str | None = None

    @model_validator(mode="after")
    def validate_execution_boundary(self) -> RouteDecision:
        """Ambiguous requests must stop for clarification instead of starting work."""

        if self.intent == "ambiguous":
            if self.execution_class is not None:
                raise ValueError("Ambiguous routes must not select an execution class")
            if self.clarification_question is None:
                raise ValueError("Ambiguous routes require a clarification question")
            return self

        if self.execution_class is None:
            raise ValueError("Non-ambiguous routes require an execution class")
        if self.clarification_question is not None:
            raise ValueError("Non-ambiguous routes must not include a clarification question")
        return self
