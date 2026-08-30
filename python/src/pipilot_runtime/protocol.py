"""JSONL stdin/stdout adapter for the Python Runtime."""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import TextIO, cast

from pydantic import ValidationError

from .configuration import RuntimeConfigurationError, load_deepseek_configuration
from .deepseek_provider import DeepSeekProvider, ModelProviderError
from .runtime import PiPilotRuntime
from .types import PROTOCOL_VERSION, ProtocolError, RuntimeError, RuntimeMessage, parse_host_message


def serialize_message(message: RuntimeMessage) -> str:
    """Serialize one Runtime event as a strict JSONL record."""

    return json.dumps(message.model_dump(by_alias=True, exclude_none=True), ensure_ascii=False, separators=(",", ":"))


def _error_identifiers(payload: object) -> tuple[str, str]:
    if not isinstance(payload, Mapping):
        return "protocol", "protocol"

    record = cast(Mapping[str, object], payload)
    task_id = record.get("taskId")
    request_id = record.get("requestId")
    return (
        task_id if isinstance(task_id, str) and task_id else "protocol",
        request_id if isinstance(request_id, str) and request_id else "protocol",
    )


def _protocol_error(payload: object, code: str, text: str, fatal: bool = False) -> RuntimeError:
    task_id, request_id = _error_identifiers(payload)
    return RuntimeError(
        protocolVersion=PROTOCOL_VERSION,
        taskId=task_id,
        requestId=request_id,
        code=code,
        message=text,
        fatal=fatal,
    )


def run_jsonl(
    input_stream: TextIO,
    output_stream: TextIO,
    error_stream: TextIO,
    runtime: PiPilotRuntime | None = None,
) -> int:
    """Run the Runtime protocol until stdin closes."""

    active_runtime = runtime or PiPilotRuntime()
    for raw_line in input_stream:
        line = raw_line.rstrip("\r\n")
        if not line:
            continue

        try:
            payload = json.loads(line)
        except json.JSONDecodeError as error:
            response: RuntimeMessage = _protocol_error(None, "invalid_json", error.msg)
            output_stream.write(f"{serialize_message(response)}\n")
            output_stream.flush()
            continue

        try:
            message = parse_host_message(payload)
        except (ProtocolError, ValidationError) as error:
            response = _protocol_error(payload, "invalid_message", str(error))
            output_stream.write(f"{serialize_message(response)}\n")
            output_stream.flush()
            continue

        try:
            responses = active_runtime.handle(message)
        except ModelProviderError as error:
            responses = [_protocol_error(payload, "model_unavailable", str(error))]

        for response in responses:
            output_stream.write(f"{serialize_message(response)}\n")
            output_stream.flush()

    error_stream.write("PiCode Runtime stdin closed.\n")
    error_stream.flush()
    return 0


def main() -> int:
    try:
        configuration = load_deepseek_configuration()
    except RuntimeConfigurationError as error:
        sys.stderr.write(f"PiCode Runtime configuration error: {error}\n")
        return 2

    state_directory = Path.cwd() / ".picode"
    runtime = (
        PiPilotRuntime(model_provider=DeepSeekProvider(configuration), trace_directory=state_directory / "traces")
        if configuration is not None
        else PiPilotRuntime(trace_directory=state_directory / "traces")
    )
    return run_jsonl(sys.stdin, sys.stdout, sys.stderr, runtime)
