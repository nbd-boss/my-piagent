import { fileURLToPath } from "node:url";
import { describe, expect, test } from "vitest";
import type { RuntimeMessage, TaskFinished, TaskState } from "../src/pipilot/protocol.ts";
import { createPythonRuntimeLaunch, RuntimeClient, startPythonRuntime } from "../src/pipilot/runtime-client.ts";

const fixturePath = fileURLToPath(new URL("./fixtures/pipilot-runtime-fixture.mjs", import.meta.url));

function waitForFinished(client: RuntimeClient): Promise<TaskFinished> {
	return new Promise((resolve) => {
		let unsubscribe = () => {};
		unsubscribe = client.subscribe((message: RuntimeMessage) => {
			if (message.type === "task_finished") {
				unsubscribe();
				resolve(message);
			}
		});
	});
}

function waitForTaskState(client: RuntimeClient): Promise<TaskState> {
	return new Promise((resolve) => {
		let unsubscribe = () => {};
		unsubscribe = client.subscribe((message: RuntimeMessage) => {
			if (message.type === "task_state") {
				unsubscribe();
				resolve(message);
			}
		});
	});
}

function waitForAssistantDelta(client: RuntimeClient): Promise<string> {
	return new Promise((resolve) => {
		let unsubscribe = () => {};
		unsubscribe = client.subscribe((message: RuntimeMessage) => {
			if (message.type === "assistant_delta") {
				unsubscribe();
				resolve(message.delta);
			}
		});
	});
}

describe("PiPilot RuntimeClient", () => {
	test("reports a Runtime process that exits before the handshake", async () => {
		await expect(
			RuntimeClient.start({ command: process.execPath, args: ["-e", "process.exit(1)"], startupTimeoutMs: 1_000 }),
		).rejects.toThrow("Python Runtime exited with code 1");
	});

	test("handshakes with a local Runtime and forwards user messages", async () => {
		const client = await RuntimeClient.start({ command: process.execPath, args: [fixturePath] });
		try {
			const finished = waitForFinished(client);
			client.sendUserMessage("task-1", "Explain this repository");

			await expect(finished).resolves.toMatchObject({ status: "success", summary: "fixture complete" });
		} finally {
			client.dispose();
		}
	});

	test("forwards cancellation to the Runtime", async () => {
		const client = await RuntimeClient.start({ command: process.execPath, args: [fixturePath] });
		try {
			const finished = waitForFinished(client);
			client.cancel("task-1", "User changed the request");

			await expect(finished).resolves.toMatchObject({
				status: "cancelled",
				summary: "User changed the request",
			});
		} finally {
			client.dispose();
		}
	});

	test("forwards clarification responses as steering messages", async () => {
		const client = await RuntimeClient.start({ command: process.execPath, args: [fixturePath] });
		try {
			const delta = waitForAssistantDelta(client);
			client.steer("task-1", "Only inspect the authentication flow.");

			await expect(delta).resolves.toBe("fixture:steer:Only inspect the authentication flow.");
		} finally {
			client.dispose();
		}
	});

	test("requests a task state from the Runtime", async () => {
		const client = await RuntimeClient.start({ command: process.execPath, args: [fixturePath] });
		try {
			const taskState = waitForTaskState(client);
			client.getTaskStatus("missing-task");

			await expect(taskState).resolves.toMatchObject({ found: false, taskId: "missing-task" });
		} finally {
			client.dispose();
		}
	});

	test.skipIf(process.env.PIPILOT_PYTHON === undefined)("connects to the real Python Runtime", async () => {
		const pythonPath = process.env.PIPILOT_PYTHON;
		if (!pythonPath) {
			throw new Error("PIPILOT_PYTHON must be set when this test is enabled");
		}
		const sourcePath = fileURLToPath(new URL("../../../python/src", import.meta.url));
		const client = await RuntimeClient.start(createPythonRuntimeLaunch({ pythonPath, sourcePath }));
		try {
			const finished = waitForFinished(client);
			client.sendUserMessage("task-1", "Explain this repository");

			await expect(finished).resolves.toMatchObject({
				status: "success",
				summary: "Intent route decided; Agent Loop is not connected yet.",
			});
		} finally {
			client.dispose();
		}
	});

	test.skipIf(process.env.PIPILOT_PYTHON === undefined)("discovers the project virtual environment", async () => {
		const workspaceDirectory = fileURLToPath(new URL("../../../", import.meta.url));
		const sourcePath = fileURLToPath(new URL("../../../python/src", import.meta.url));
		const client = await startPythonRuntime({ workspaceDirectory, sourcePath, environment: { PIPILOT_MODEL: "" } });
		try {
			const finished = waitForFinished(client);
			client.sendUserMessage("task-1", "Explain this repository");

			await expect(finished).resolves.toMatchObject({ status: "success" });
		} finally {
			client.dispose();
		}
	});
});
