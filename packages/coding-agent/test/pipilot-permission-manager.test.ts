import { describe, expect, test } from "vitest";
import { PermissionManager } from "../src/pipilot/permission-manager.ts";

describe("PiPilot PermissionManager", () => {
	test("allows read-only tools without confirmation", () => {
		const decision = new PermissionManager("C:/workspace").request("task-1", "call-1", { tool: "read" });

		expect(decision).toMatchObject({ status: "allowed", permission: "read-only" });
	});

	test("grants workspace writes only to the current task", () => {
		const manager = new PermissionManager("C:/workspace");
		const request = manager.request("task-1", "call-1", { tool: "edit", targetPath: "C:/workspace/src/login.ts" });
		const granted = manager.respond("task-1", true);

		expect(request).toMatchObject({ status: "requires_confirmation", permission: "workspace-write" });
		expect(granted).toMatchObject({ status: "allowed", permission: "workspace-write" });
		expect(manager.hasWorkspaceWrite("task-1")).toBe(true);
		expect(manager.hasWorkspaceWrite("task-2")).toBe(false);
	});

	test("denies workspace writes outside the current repository", () => {
		const decision = new PermissionManager("C:/workspace").request("task-1", "call-1", {
			tool: "write",
			targetPath: "C:/outside/file.ts",
		});

		expect(decision.status).toBe("denied");
	});

	test("requires a new confirmation for every high-risk operation", () => {
		const manager = new PermissionManager("C:/workspace");
		const first = manager.request("task-1", "call-1", { tool: "bash", command: "git push origin main" });
		manager.respond("task-1", true);
		const second = manager.request("task-1", "call-2", { tool: "bash", command: "git push origin main" });

		expect(first).toMatchObject({ status: "requires_confirmation", permission: "high-risk" });
		expect(second).toMatchObject({ status: "requires_confirmation", permission: "high-risk" });
	});

	test("clears workspace write grants when a task ends", () => {
		const manager = new PermissionManager("C:/workspace");
		manager.request("task-1", "call-1", { tool: "edit", targetPath: "C:/workspace/login.ts" });
		manager.respond("task-1", true);

		manager.clear("task-1");

		expect(manager.hasWorkspaceWrite("task-1")).toBe(false);
	});
});
