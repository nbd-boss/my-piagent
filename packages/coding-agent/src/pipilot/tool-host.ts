import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import type { AgentToolResult } from "@earendil-works/pi-agent-core";
import { createAllTools, type ToolName } from "../core/tools/index.ts";
import { type PermissionDecision, PermissionManager, type ToolOperation } from "./permission-manager.ts";
import { type PermissionRequired, PIPILOT_PROTOCOL_VERSION, type ToolRequest, type ToolResult } from "./protocol.ts";

export type ToolHostResult = ToolResult | PermissionRequired;

export type ToolHostLifecycleEvent =
	| { type: "tool_started"; request: ToolRequest }
	| { type: "tool_finished"; result: ToolResult };

export interface ToolExecutionRecord {
	taskId: string;
	toolCallId: string;
	tool: string;
	argumentsFingerprint?: string;
	status: ToolResult["status"];
	durationMs: number;
	truncated?: boolean;
	outputReference?: string;
	exitCode?: number;
	errorCategory?: ToolResult["errorCategory"];
}

interface PendingToolRequest {
	request: ToolRequest;
}

export interface ToolHostOptions {
	timeoutMs?: number;
}

const TOOL_NAMES = new Set<ToolName>(["read", "grep", "find", "ls", "edit", "write", "bash", "powershell"]);

/**
 * Executes Pi's existing local tools for PiCode after applying a final permission check.
 * Python decides what to do; this class owns only local execution and cancellation.
 */
export class ToolHost {
	readonly #tools;
	readonly #permissions: PermissionManager;
	readonly #workspaceDirectory: string;
	readonly #timeoutMs: number;
	readonly #pending = new Map<string, PendingToolRequest>();
	readonly #activeControllers = new Map<string, AbortController>();
	readonly #fileBaselines = new Map<string, Map<string, string | undefined>>();
	readonly #listeners = new Set<(event: ToolHostLifecycleEvent) => void>();
	readonly #records = new Map<string, ToolExecutionRecord[]>();

	constructor(workspaceDirectory: string, options: ToolHostOptions = {}) {
		this.#workspaceDirectory = resolve(workspaceDirectory);
		this.#tools = createAllTools(this.#workspaceDirectory);
		this.#permissions = new PermissionManager(this.#workspaceDirectory);
		this.#timeoutMs = options.timeoutMs ?? 30_000;
	}

	subscribe(listener: (event: ToolHostLifecycleEvent) => void): () => void {
		this.#listeners.add(listener);
		return () => this.#listeners.delete(listener);
	}

	executionRecords(taskId: string): readonly ToolExecutionRecord[] {
		return this.#records.get(taskId) ?? [];
	}

	async handle(request: ToolRequest, signal?: AbortSignal): Promise<ToolHostResult> {
		const validationError = this.#validate(request);
		if (validationError) return this.#failed(request, "invalid_request", validationError, 0);

		const permission = this.#permissions.request(request.taskId, request.toolCallId, this.#operationFor(request));
		if (permission.status === "requires_confirmation") {
			this.#pending.set(request.taskId, { request });
			return this.#permissionRequired(request, permission);
		}
		if (permission.status === "denied") {
			return this.#failed(request, "permission", permission.reason, 0);
		}
		return this.#execute(request, signal);
	}

	async respondToPermission(taskId: string, granted: boolean, signal?: AbortSignal): Promise<ToolResult> {
		const pending = this.#pending.get(taskId);
		const decision = this.#permissions.respond(taskId, granted);
		this.#pending.delete(taskId);
		if (!pending) {
			return this.#result(taskId, "permission", "permission", "failed", "", 0, {
				errorCategory: "permission",
			});
		}
		if (decision.status !== "allowed") {
			return this.#failed(pending.request, "permission", decision.reason, 0);
		}
		return this.#execute(pending.request, signal);
	}

	cancel(taskId: string): void {
		this.#activeControllers.get(taskId)?.abort();
		this.#activeControllers.delete(taskId);
		this.#pending.delete(taskId);
		this.#permissions.clear(taskId);
		this.#fileBaselines.delete(taskId);
	}

	#validate(request: ToolRequest): string | undefined {
		if (!TOOL_NAMES.has(request.tool as ToolName)) return `Unsupported tool: ${request.tool}`;
		if (
			(request.tool === "read" || request.tool === "edit" || request.tool === "write") &&
			!this.#stringArg(request, "path")
		) {
			return `${request.tool} requires a string path argument.`;
		}
		if ((request.tool === "bash" || request.tool === "powershell") && !this.#stringArg(request, "command")) {
			return `${request.tool} requires a string command argument.`;
		}
		return undefined;
	}

	#operationFor(request: ToolRequest): ToolOperation {
		return {
			tool: request.tool,
			targetPath: request.tool === "edit" || request.tool === "write" ? this.#stringArg(request, "path") : undefined,
			command:
				request.tool === "bash" || request.tool === "powershell" ? this.#stringArg(request, "command") : undefined,
		};
	}

	async #execute(request: ToolRequest, signal?: AbortSignal): Promise<ToolResult> {
		const startedAt = Date.now();
		const targetPath = this.#writeTargetPath(request);
		if (targetPath) {
			const conflict = await this.#checkFileBaseline(request.taskId, targetPath);
			if (conflict) return this.#failed(request, "conflict", conflict, Date.now() - startedAt);
		}

		const controller = new AbortController();
		this.#activeControllers.set(request.taskId, controller);
		const timeout = setTimeout(() => controller.abort(), this.#timeoutMs);
		const abort = () => controller.abort();
		signal?.addEventListener("abort", abort, { once: true });
		this.#emit({ type: "tool_started", request });
		let response: ToolResult;

		try {
			const tool = this.#tools[request.tool as ToolName];
			const result = await tool.execute(request.toolCallId, request.arguments, controller.signal);
			if (targetPath) await this.#saveFileBaseline(request.taskId, targetPath);
			response = this.#result(
				request.taskId,
				request.requestId,
				request.toolCallId,
				"success",
				this.#textContent(result),
				Date.now() - startedAt,
				{ ...this.#requestMetadata(request), ...this.#resultMetadata(result) },
			);
		} catch (error) {
			const timedOut = !signal?.aborted && controller.signal.aborted;
			const cancelled = signal?.aborted || controller.signal.aborted;
			const message = error instanceof Error ? error.message : String(error);
			const exitCode = this.#exitCodeFromMessage(message);
			response = this.#result(
				request.taskId,
				request.requestId,
				request.toolCallId,
				cancelled ? "cancelled" : "failed",
				message,
				Date.now() - startedAt,
				{
					...this.#requestMetadata(request),
					errorCategory: timedOut ? "timeout" : cancelled ? "cancelled" : "execution",
					...(exitCode === undefined ? {} : { exitCode }),
				},
			);
		} finally {
			clearTimeout(timeout);
			signal?.removeEventListener("abort", abort);
			this.#activeControllers.delete(request.taskId);
		}
		this.#record(request, response);
		this.#emit({ type: "tool_finished", result: response });
		return response;
	}

	#permissionRequired(request: ToolRequest, decision: PermissionDecision): PermissionRequired {
		if (decision.permission === "read-only") {
			throw new Error("Read-only operations must not request confirmation");
		}
		return {
			protocolVersion: PIPILOT_PROTOCOL_VERSION,
			taskId: request.taskId,
			requestId: request.requestId,
			type: "permission_required",
			permission: decision.permission,
			reason: decision.reason,
		};
	}

	#failed(
		request: ToolRequest,
		errorCategory: ToolResult["errorCategory"],
		message: string,
		durationMs: number,
	): ToolResult {
		return this.#result(request.taskId, request.requestId, request.toolCallId, "failed", message, durationMs, {
			...this.#requestMetadata(request),
			errorCategory,
		});
	}

	#result(
		taskId: string,
		requestId: string,
		toolCallId: string,
		status: ToolResult["status"],
		content: string,
		durationMs: number,
		extra: Pick<
			ToolResult,
			"argumentsFingerprint" | "errorCategory" | "exitCode" | "outputReference" | "tool" | "truncated"
		> = {},
	): ToolResult {
		return {
			protocolVersion: PIPILOT_PROTOCOL_VERSION,
			taskId,
			requestId,
			type: "tool_result",
			toolCallId,
			status,
			content,
			durationMs,
			...extra,
		};
	}

	#stringArg(request: ToolRequest, name: string): string | undefined {
		const value = request.arguments[name];
		return typeof value === "string" && value.length > 0 ? value : undefined;
	}

	#textContent(result: AgentToolResult<unknown>): string {
		return result.content
			.filter((block) => block.type === "text")
			.map((block) => block.text)
			.join("\n");
	}

	#requestMetadata(request: ToolRequest): Pick<ToolResult, "argumentsFingerprint" | "tool"> {
		return { tool: request.tool, argumentsFingerprint: this.#argumentsFingerprint(request.arguments) };
	}

	#argumentsFingerprint(arguments_: Record<string, unknown>): string {
		return createHash("sha256")
			.update(JSON.stringify(this.#canonicalize(arguments_)))
			.digest("hex");
	}

	#canonicalize(value: unknown): unknown {
		if (Array.isArray(value)) return value.map((item) => this.#canonicalize(item));
		if (typeof value !== "object" || value === null) return value;
		const record = value as Record<string, unknown>;
		return Object.fromEntries(
			Object.keys(record)
				.sort()
				.map((key) => [key, this.#canonicalize(record[key])]),
		);
	}

	#resultMetadata(result: AgentToolResult<unknown>): Pick<ToolResult, "outputReference" | "truncated"> {
		if (typeof result.details !== "object" || result.details === null || Array.isArray(result.details)) return {};
		const details = result.details as Record<string, unknown>;
		const truncation = details.truncation;
		const truncated =
			typeof truncation === "object" && truncation !== null && "truncated" in truncation
				? (truncation as { truncated?: unknown }).truncated
				: undefined;
		return {
			...(typeof truncated === "boolean" ? { truncated } : {}),
			...(typeof details.fullOutputPath === "string" ? { outputReference: details.fullOutputPath } : {}),
		};
	}

	#record(request: ToolRequest, result: ToolResult): void {
		const records = this.#records.get(request.taskId) ?? [];
		records.push({
			taskId: request.taskId,
			toolCallId: request.toolCallId,
			tool: request.tool,
			...(result.argumentsFingerprint === undefined ? {} : { argumentsFingerprint: result.argumentsFingerprint }),
			status: result.status,
			durationMs: result.durationMs ?? 0,
			...(result.truncated === undefined ? {} : { truncated: result.truncated }),
			...(result.outputReference === undefined ? {} : { outputReference: result.outputReference }),
			...(result.exitCode === undefined ? {} : { exitCode: result.exitCode }),
			...(result.errorCategory === undefined ? {} : { errorCategory: result.errorCategory }),
		});
		this.#records.set(request.taskId, records);
	}

	#exitCodeFromMessage(message: string): number | undefined {
		const match = /Command exited with code (\d+)/.exec(message);
		return match ? Number(match[1]) : undefined;
	}

	#writeTargetPath(request: ToolRequest): string | undefined {
		if (request.tool !== "edit" && request.tool !== "write") return undefined;
		const path = this.#stringArg(request, "path");
		return path ? resolve(this.#workspaceDirectory, path) : undefined;
	}

	async #checkFileBaseline(taskId: string, targetPath: string): Promise<string | undefined> {
		const baselines = this.#fileBaselines.get(taskId) ?? new Map<string, string | undefined>();
		this.#fileBaselines.set(taskId, baselines);
		const current = await this.#fileFingerprint(targetPath);
		const known = baselines.get(targetPath);
		if (!baselines.has(targetPath)) {
			baselines.set(targetPath, current);
			return undefined;
		}
		return known === current ? undefined : `Write stopped because ${targetPath} changed outside this task.`;
	}

	async #saveFileBaseline(taskId: string, targetPath: string): Promise<void> {
		const baselines = this.#fileBaselines.get(taskId) ?? new Map<string, string | undefined>();
		baselines.set(targetPath, await this.#fileFingerprint(targetPath));
		this.#fileBaselines.set(taskId, baselines);
	}

	async #fileFingerprint(path: string): Promise<string | undefined> {
		try {
			return createHash("sha256")
				.update(await readFile(path))
				.digest("hex");
		} catch (error) {
			if (error instanceof Error && "code" in error && error.code === "ENOENT") return undefined;
			throw error;
		}
	}

	#emit(event: ToolHostLifecycleEvent): void {
		for (const listener of this.#listeners) listener(event);
	}
}
