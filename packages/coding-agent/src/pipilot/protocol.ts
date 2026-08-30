import { serializeJsonLine } from "../modes/rpc/jsonl.ts";

export const PIPILOT_PROTOCOL_VERSION = 1;

export type ExecutionClass = "high_frequency" | "long_task_agent";
export type PermissionLevel = "read-only" | "workspace-write" | "high-risk";
export type Intent = "question" | "inspect" | "change" | "review" | "run" | "ambiguous";
export type TaskResultStatus = "success" | "partial" | "unverified" | "blocked" | "failed" | "cancelled";
export type ToolErrorCategory = "permission" | "invalid_request" | "execution" | "cancelled" | "timeout" | "conflict";

interface ProtocolEnvelope {
	protocolVersion: number;
	taskId: string;
	requestId: string;
	type: string;
}

export interface HostHello extends ProtocolEnvelope {
	type: "host_hello";
}

export interface UserMessage extends ProtocolEnvelope {
	type: "user_message";
	content: string;
}

export interface Steer extends ProtocolEnvelope {
	type: "steer";
	content: string;
}

export interface PermissionResponse extends ProtocolEnvelope {
	type: "permission_response";
	granted: boolean;
}

export interface Cancel extends ProtocolEnvelope {
	type: "cancel";
	reason?: string;
}

export interface ToolResult extends ProtocolEnvelope {
	type: "tool_result";
	toolCallId: string;
	tool?: string;
	argumentsFingerprint?: string;
	status: "success" | "failed" | "cancelled";
	content: string;
	durationMs?: number;
	truncated?: boolean;
	outputReference?: string;
	exitCode?: number;
	errorCategory?: ToolErrorCategory;
}

export interface TaskStatus extends ProtocolEnvelope {
	type: "task_status";
}

export type HostMessage = HostHello | UserMessage | Steer | PermissionResponse | Cancel | ToolResult | TaskStatus;

export interface RuntimeReady extends ProtocolEnvelope {
	type: "runtime_ready";
	capabilities: string[];
}

export interface AssistantDelta extends ProtocolEnvelope {
	type: "assistant_delta";
	delta: string;
}

export interface RouteDecided extends ProtocolEnvelope {
	type: "route_decided";
	intent: Intent;
	executionClass: ExecutionClass | null;
	clarificationQuestion?: string;
	reason?: string;
}

export interface PlanUpdated extends ProtocolEnvelope {
	type: "plan_updated";
	summary: string;
}

export interface ToolRequest extends ProtocolEnvelope {
	type: "tool_request";
	toolCallId: string;
	tool: string;
	arguments: Record<string, unknown>;
}

export interface PermissionRequired extends ProtocolEnvelope {
	type: "permission_required";
	permission: Exclude<PermissionLevel, "read-only">;
	reason: string;
}

export interface VerificationUpdated extends ProtocolEnvelope {
	type: "verification_updated";
	status: "pending" | "passed" | "failed" | "skipped";
	summary: string;
}

export interface TaskFinished extends ProtocolEnvelope {
	type: "task_finished";
	status: TaskResultStatus;
	summary: string;
}

export interface RuntimeError extends ProtocolEnvelope {
	type: "runtime_error";
	code: string;
	message: string;
	fatal: boolean;
}

export interface TaskState extends ProtocolEnvelope {
	type: "task_state";
	found: boolean;
	latestRequest?: string;
	intent?: string;
	executionClass?: string;
	status?: string;
}

export type RuntimeMessage =
	| RuntimeReady
	| AssistantDelta
	| RouteDecided
	| PlanUpdated
	| ToolRequest
	| PermissionRequired
	| VerificationUpdated
	| TaskFinished
	| RuntimeError
	| TaskState;

export class PiPilotProtocolError extends Error {
	constructor(message: string) {
		super(message);
		this.name = "PiPilotProtocolError";
	}
}

function asRecord(value: unknown): Record<string, unknown> {
	if (typeof value !== "object" || value === null || Array.isArray(value)) {
		throw new PiPilotProtocolError("Protocol message must be an object");
	}
	return value as Record<string, unknown>;
}

function readString(record: Record<string, unknown>, key: string): string {
	const value = record[key];
	if (typeof value !== "string" || value.length === 0) {
		throw new PiPilotProtocolError(`Protocol field ${key} must be a non-empty string`);
	}
	return value;
}

function readOptionalString(record: Record<string, unknown>, key: string): string | undefined {
	const value = record[key];
	if (value === undefined) return undefined;
	if (typeof value !== "string" || value.length === 0) {
		throw new PiPilotProtocolError(`Protocol field ${key} must be a non-empty string when provided`);
	}
	return value;
}

function readBoolean(record: Record<string, unknown>, key: string): boolean {
	const value = record[key];
	if (typeof value !== "boolean") {
		throw new PiPilotProtocolError(`Protocol field ${key} must be a boolean`);
	}
	return value;
}

function readStringArray(record: Record<string, unknown>, key: string): string[] {
	const value = record[key];
	if (!Array.isArray(value) || value.some((item) => typeof item !== "string")) {
		throw new PiPilotProtocolError(`Protocol field ${key} must be an array of strings`);
	}
	return value;
}

function readEnum<T extends string>(record: Record<string, unknown>, key: string, values: readonly T[]): T {
	const value = readString(record, key);
	if (!values.includes(value as T)) {
		throw new PiPilotProtocolError(`Protocol field ${key} has an unsupported value: ${value}`);
	}
	return value as T;
}

function readNullableEnum<T extends string>(
	record: Record<string, unknown>,
	key: string,
	values: readonly T[],
): T | null {
	if (record[key] === null) return null;
	return readEnum(record, key, values);
}

function readEnvelope(value: unknown): ProtocolEnvelope {
	const record = asRecord(value);
	const protocolVersion = record.protocolVersion;
	if (protocolVersion !== PIPILOT_PROTOCOL_VERSION) {
		throw new PiPilotProtocolError(
			`Unsupported protocol version ${String(protocolVersion)}; expected ${PIPILOT_PROTOCOL_VERSION}`,
		);
	}

	return {
		protocolVersion,
		taskId: readString(record, "taskId"),
		requestId: readString(record, "requestId"),
		type: readString(record, "type"),
	};
}

export function parseRuntimeMessage(value: unknown): RuntimeMessage {
	const envelope = readEnvelope(value);
	const record = asRecord(value);

	switch (envelope.type) {
		case "runtime_ready":
			return { ...envelope, type: "runtime_ready", capabilities: readStringArray(record, "capabilities") };
		case "assistant_delta":
			return { ...envelope, type: "assistant_delta", delta: readString(record, "delta") };
		case "route_decided":
			return validateRouteDecision({
				...envelope,
				type: "route_decided",
				intent: readEnum(record, "intent", ["question", "inspect", "change", "review", "run", "ambiguous"]),
				executionClass: readNullableEnum(record, "executionClass", ["high_frequency", "long_task_agent"]),
				clarificationQuestion: readOptionalString(record, "clarificationQuestion"),
				reason: readOptionalString(record, "reason"),
			});
		case "plan_updated":
			return { ...envelope, type: "plan_updated", summary: readString(record, "summary") };
		case "tool_request": {
			const argumentsValue = asRecord(record.arguments);
			return {
				...envelope,
				type: "tool_request",
				toolCallId: readString(record, "toolCallId"),
				tool: readString(record, "tool"),
				arguments: argumentsValue,
			};
		}
		case "permission_required":
			return {
				...envelope,
				type: "permission_required",
				permission: readEnum(record, "permission", ["workspace-write", "high-risk"]),
				reason: readString(record, "reason"),
			};
		case "verification_updated":
			return {
				...envelope,
				type: "verification_updated",
				status: readEnum(record, "status", ["pending", "passed", "failed", "skipped"]),
				summary: readString(record, "summary"),
			};
		case "task_finished":
			return {
				...envelope,
				type: "task_finished",
				status: readEnum(record, "status", ["success", "partial", "unverified", "blocked", "failed", "cancelled"]),
				summary: readString(record, "summary"),
			};
		case "runtime_error":
			return {
				...envelope,
				type: "runtime_error",
				code: readString(record, "code"),
				message: readString(record, "message"),
				fatal: readBoolean(record, "fatal"),
			};
		case "task_state":
			return {
				...envelope,
				type: "task_state",
				found: readBoolean(record, "found"),
				latestRequest: readOptionalString(record, "latestRequest"),
				intent: readOptionalString(record, "intent"),
				executionClass: readOptionalString(record, "executionClass"),
				status: readOptionalString(record, "status"),
			};
		default:
			throw new PiPilotProtocolError(`Unsupported Runtime message type: ${envelope.type}`);
	}
}

function validateRouteDecision(message: RouteDecided): RouteDecided {
	if (message.intent === "ambiguous") {
		if (message.executionClass !== null) {
			throw new PiPilotProtocolError("Ambiguous routes must not select an execution class");
		}
		if (message.clarificationQuestion === undefined) {
			throw new PiPilotProtocolError("Ambiguous routes require a clarification question");
		}
		return message;
	}

	if (message.executionClass === null) {
		throw new PiPilotProtocolError("Non-ambiguous routes require an execution class");
	}
	if (message.clarificationQuestion !== undefined) {
		throw new PiPilotProtocolError("Non-ambiguous routes must not include a clarification question");
	}
	return message;
}

export function serializeHostMessage(message: HostMessage): string {
	if (message.protocolVersion !== PIPILOT_PROTOCOL_VERSION) {
		throw new PiPilotProtocolError(
			`Unsupported protocol version ${message.protocolVersion}; expected ${PIPILOT_PROTOCOL_VERSION}`,
		);
	}
	return serializeJsonLine(message);
}
