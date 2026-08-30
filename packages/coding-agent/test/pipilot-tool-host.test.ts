import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, test } from "vitest";
import { PIPILOT_PROTOCOL_VERSION, type ToolRequest } from "../src/pipilot/protocol.ts";
import { ToolHost } from "../src/pipilot/tool-host.ts";

function request(tool: string, arguments_: Record<string, unknown>): ToolRequest {
	return {
		protocolVersion: PIPILOT_PROTOCOL_VERSION,
		taskId: "task-1",
		requestId: "request-1",
		type: "tool_request",
		toolCallId: "call-1",
		tool,
		arguments: arguments_,
	};
}

describe("PiPilot ToolHost", () => {
	test("runs a read-only request through Pi's existing read tool", async () => {
		const workspace = await mkdtemp(join(tmpdir(), "pipilot-tool-host-"));
		const sourcePath = join(workspace, "source.txt");
		await writeFile(sourcePath, "hello from PiPilot", "utf8");
		const host = new ToolHost(workspace);

		const result = await host.handle(request("read", { path: sourcePath }));

		expect(result).toMatchObject({
			type: "tool_result",
			status: "success",
			toolCallId: "call-1",
			tool: "read",
		});
		if (result.type === "tool_result") expect(result.content).toContain("hello from PiPilot");
		if (result.type === "tool_result") expect(result.argumentsFingerprint).toMatch(/^[a-f0-9]{64}$/);
	});

	test("emits start and finish events for every executed tool", async () => {
		const workspace = await mkdtemp(join(tmpdir(), "pipilot-tool-host-"));
		const sourcePath = join(workspace, "source.txt");
		await writeFile(sourcePath, "hello", "utf8");
		const host = new ToolHost(workspace);
		const events: string[] = [];
		host.subscribe((event) => events.push(event.type));

		await host.handle(request("read", { path: sourcePath }));

		expect(events).toEqual(["tool_started", "tool_finished"]);
		expect(host.executionRecords("task-1")).toMatchObject([
			{ tool: "read", toolCallId: "call-1", status: "success" },
		]);
	});

	test("preserves truncation metadata from Pi tools", async () => {
		const workspace = await mkdtemp(join(tmpdir(), "pipilot-tool-host-"));
		const sourcePath = join(workspace, "large.txt");
		await writeFile(
			sourcePath,
			`${Array.from({ length: 2_001 }, (_, index) => `line ${index}`).join("\n")}\n`,
			"utf8",
		);
		const host = new ToolHost(workspace);

		const result = await host.handle(request("read", { path: sourcePath }));

		expect(result).toMatchObject({ type: "tool_result", status: "success", truncated: true });
	});

	test("waits for confirmation before writing and then runs Pi's write tool", async () => {
		const workspace = await mkdtemp(join(tmpdir(), "pipilot-tool-host-"));
		const targetPath = join(workspace, "created.txt");
		const host = new ToolHost(workspace);

		const pending = await host.handle(request("write", { path: "created.txt", content: "created by tool host" }));
		expect(pending).toMatchObject({ type: "permission_required", permission: "workspace-write" });

		const result = await host.respondToPermission("task-1", true);
		expect(result).toMatchObject({ type: "tool_result", status: "success", toolCallId: "call-1" });
		await expect(readFile(targetPath, "utf8")).resolves.toBe("created by tool host");
	});

	test("rejects writes outside the workspace before execution", async () => {
		const workspace = await mkdtemp(join(tmpdir(), "pipilot-tool-host-"));
		const host = new ToolHost(workspace);

		const result = await host.handle(request("write", { path: join(tmpdir(), "outside.txt"), content: "blocked" }));

		expect(result).toMatchObject({ type: "tool_result", status: "failed", errorCategory: "permission" });
	});

	test("requires confirmation for a high-risk shell command and does not run it after denial", async () => {
		const workspace = await mkdtemp(join(tmpdir(), "pipilot-tool-host-"));
		const host = new ToolHost(workspace);

		const pending = await host.handle(request("powershell", { command: "git push origin main" }));
		expect(pending).toMatchObject({ type: "permission_required", permission: "high-risk" });

		const result = await host.respondToPermission("task-1", false);
		expect(result).toMatchObject({ type: "tool_result", status: "failed", errorCategory: "permission" });
	});

	test("rejects unsupported tools without creating a permission request", async () => {
		const workspace = await mkdtemp(join(tmpdir(), "pipilot-tool-host-"));
		const host = new ToolHost(workspace);

		const result = await host.handle(request("network", {}));

		expect(result).toMatchObject({ type: "tool_result", status: "failed", errorCategory: "invalid_request" });
	});

	test("stops a second write when the target changed outside the task", async () => {
		const workspace = await mkdtemp(join(tmpdir(), "pipilot-tool-host-"));
		const targetPath = join(workspace, "tracked.txt");
		const host = new ToolHost(workspace);

		await host.handle(request("write", { path: "tracked.txt", content: "agent version" }));
		await host.respondToPermission("task-1", true);
		await writeFile(targetPath, "user version", "utf8");

		const result = await host.handle(request("write", { path: "tracked.txt", content: "second agent version" }));

		expect(result).toMatchObject({ type: "tool_result", status: "failed", errorCategory: "conflict" });
		await expect(readFile(targetPath, "utf8")).resolves.toBe("user version");
	});
});
