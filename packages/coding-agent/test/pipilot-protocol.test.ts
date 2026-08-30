import { describe, expect, test } from "vitest";
import {
	PIPILOT_PROTOCOL_VERSION,
	PiPilotProtocolError,
	parseRuntimeMessage,
	serializeHostMessage,
} from "../src/pipilot/protocol.ts";

describe("PiPilot protocol", () => {
	test("serializes a Host message as JSONL", () => {
		const line = serializeHostMessage({
			protocolVersion: PIPILOT_PROTOCOL_VERSION,
			taskId: "task-1",
			requestId: "request-1",
			type: "user_message",
			content: "Explain the repository",
		});

		expect(line.endsWith("\n")).toBe(true);
		expect(JSON.parse(line)).toMatchObject({ type: "user_message", taskId: "task-1" });
	});

	test("parses a structured Runtime tool request", () => {
		const message = parseRuntimeMessage({
			protocolVersion: PIPILOT_PROTOCOL_VERSION,
			taskId: "task-1",
			requestId: "request-1",
			type: "tool_request",
			toolCallId: "call-1",
			tool: "grep",
			arguments: { pattern: "login" },
		});

		expect(message).toEqual({
			protocolVersion: PIPILOT_PROTOCOL_VERSION,
			taskId: "task-1",
			requestId: "request-1",
			type: "tool_request",
			toolCallId: "call-1",
			tool: "grep",
			arguments: { pattern: "login" },
		});
	});

	test("parses an intent route decision", () => {
		const message = parseRuntimeMessage({
			protocolVersion: PIPILOT_PROTOCOL_VERSION,
			taskId: "task-1",
			requestId: "request-1",
			type: "route_decided",
			intent: "change",
			executionClass: "long_task_agent",
			reason: "The request requires repository changes.",
		});

		expect(message).toMatchObject({ type: "route_decided", intent: "change", executionClass: "long_task_agent" });
	});

	test("parses an ambiguous route that requests clarification", () => {
		const message = parseRuntimeMessage({
			protocolVersion: PIPILOT_PROTOCOL_VERSION,
			taskId: "task-1",
			requestId: "request-1",
			type: "route_decided",
			intent: "ambiguous",
			executionClass: null,
			clarificationQuestion: "Should I inspect the issue or change the code?",
		});

		expect(message).toMatchObject({ type: "route_decided", intent: "ambiguous", executionClass: null });
	});

	test("parses a task state response", () => {
		const message = parseRuntimeMessage({
			protocolVersion: PIPILOT_PROTOCOL_VERSION,
			taskId: "task-1",
			requestId: "request-1",
			type: "task_state",
			found: true,
			latestRequest: "Explain authentication",
			intent: "inspect",
			executionClass: "high_frequency",
			status: "routed",
		});

		expect(message).toMatchObject({ type: "task_state", found: true, executionClass: "high_frequency" });
	});

	test("rejects unknown protocol versions", () => {
		expect(() =>
			parseRuntimeMessage({
				protocolVersion: 2,
				taskId: "task-1",
				requestId: "request-1",
				type: "runtime_ready",
				capabilities: [],
			}),
		).toThrow(PiPilotProtocolError);
	});
});
