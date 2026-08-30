import { isAbsolute, relative, resolve, sep } from "node:path";
import type { PermissionLevel } from "./protocol.ts";

export type PermissionStatus = "allowed" | "requires_confirmation" | "denied";
export type RequestedPermission = Exclude<PermissionLevel, "read-only">;

export interface ToolOperation {
	tool: string;
	targetPath?: string;
	command?: string;
}

export interface PermissionDecision {
	status: PermissionStatus;
	permission: PermissionLevel;
	reason: string;
}

interface PendingPermission {
	toolCallId: string;
	permission: RequestedPermission;
	reason: string;
}

interface TaskPermissionState {
	workspaceWriteGranted: boolean;
	pending?: PendingPermission;
}

const READ_ONLY_TOOLS = new Set(["read", "grep", "find", "ls"]);
const WORKSPACE_WRITE_TOOLS = new Set(["edit", "write"]);
const HIGH_RISK_COMMAND_TERMS = ["git push", "deploy", "rm ", "remove-item", "del ", "format ", "curl |", "wget "];
const READ_ONLY_COMMAND_PREFIXES = [
	"git status",
	"git diff",
	"rg ",
	"grep ",
	"ls",
	"dir",
	"get-content",
	"cat ",
	"pwd",
];

export class PermissionManager {
	readonly #workspaceRoot: string;
	readonly #states = new Map<string, TaskPermissionState>();

	constructor(workspaceRoot: string) {
		this.#workspaceRoot = resolve(workspaceRoot);
	}

	request(taskId: string, toolCallId: string, operation: ToolOperation): PermissionDecision {
		const [permission, reason] = this.#classify(operation);
		if (permission === "workspace-write" && operation.targetPath && !this.#isWorkspacePath(operation.targetPath)) {
			return { status: "denied", permission, reason: "Write target is outside the current workspace." };
		}
		if (permission === "read-only") return { status: "allowed", permission, reason };

		const state = this.#states.get(taskId) ?? { workspaceWriteGranted: false };
		this.#states.set(taskId, state);
		if (state.pending) {
			return {
				status: "denied",
				permission,
				reason: "Another permission request is already pending for this task.",
			};
		}
		if (permission === "workspace-write" && state.workspaceWriteGranted) {
			return { status: "allowed", permission, reason };
		}

		state.pending = { toolCallId, permission, reason };
		return { status: "requires_confirmation", permission, reason };
	}

	respond(taskId: string, granted: boolean): PermissionDecision {
		const state = this.#states.get(taskId);
		if (!state?.pending) {
			return { status: "denied", permission: "read-only", reason: "This task has no pending permission request." };
		}

		const pending = state.pending;
		state.pending = undefined;
		if (!granted)
			return { status: "denied", permission: pending.permission, reason: "The user denied this operation." };
		if (pending.permission === "workspace-write") {
			state.workspaceWriteGranted = true;
			return {
				status: "allowed",
				permission: "workspace-write",
				reason: "Workspace writes are allowed for this task.",
			};
		}
		return { status: "allowed", permission: "high-risk", reason: "The user approved this high-risk operation once." };
	}

	clear(taskId: string): void {
		this.#states.delete(taskId);
	}

	hasWorkspaceWrite(taskId: string): boolean {
		return this.#states.get(taskId)?.workspaceWriteGranted ?? false;
	}

	#classify(operation: ToolOperation): [PermissionLevel, string] {
		if (READ_ONLY_TOOLS.has(operation.tool)) return ["read-only", `${operation.tool} is read-only.`];
		if (WORKSPACE_WRITE_TOOLS.has(operation.tool))
			return ["workspace-write", `${operation.tool} can modify the workspace.`];
		if (operation.tool === "bash" || operation.tool === "powershell") {
			const command = operation.command?.trim().toLowerCase() ?? "";
			if (HIGH_RISK_COMMAND_TERMS.some((term) => command.includes(term))) {
				return ["high-risk", "The command may create an external or destructive side effect."];
			}
			if (READ_ONLY_COMMAND_PREFIXES.some((prefix) => command.startsWith(prefix))) {
				return ["read-only", "The command is classified as read-only."];
			}
			return ["high-risk", "Unknown shell commands require high-risk confirmation."];
		}
		return ["high-risk", `Unknown tool ${operation.tool} requires high-risk confirmation.`];
	}

	#isWorkspacePath(targetPath: string): boolean {
		const relativePath = relative(this.#workspaceRoot, resolve(this.#workspaceRoot, targetPath));
		return (
			relativePath === "" ||
			(!relativePath.startsWith(`..${sep}`) && relativePath !== ".." && !isAbsolute(relativePath))
		);
	}
}
