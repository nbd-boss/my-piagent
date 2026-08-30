import { describe, expect, test } from "vitest";
import {
	discoverPythonRuntime,
	type PythonRuntimeCandidate,
	PythonRuntimeDiscoveryError,
	type PythonRuntimeProbe,
} from "../src/pipilot/python-discovery.ts";

const candidates: PythonRuntimeCandidate[] = [
	{ command: "configured-python", args: [], label: "configured Python" },
	{ command: "venv-python", args: [], label: "project virtual environment" },
];

function probe(
	results: Record<string, { executable: string; major: number; minor: number; hasPydantic: boolean }>,
): PythonRuntimeProbe {
	return async (candidate) => results[candidate.command];
}

describe("PiPilot Python discovery", () => {
	test("uses the first compatible interpreter with Runtime dependencies", async () => {
		const result = await discoverPythonRuntime({
			workspaceDirectory: "C:/project",
			candidates,
			probe: probe({
				"configured-python": { executable: "C:/Python312/python.exe", major: 3, minor: 12, hasPydantic: true },
			}),
		});

		expect(result).toEqual({
			pythonPath: "C:/Python312/python.exe",
			version: "3.12",
			source: "configured Python",
		});
	});

	test("skips an old interpreter and selects the project environment", async () => {
		const result = await discoverPythonRuntime({
			workspaceDirectory: "C:/project",
			candidates,
			probe: probe({
				"configured-python": { executable: "C:/Python310/python.exe", major: 3, minor: 10, hasPydantic: true },
				"venv-python": { executable: "C:/project/python/.venv/python.exe", major: 3, minor: 12, hasPydantic: true },
			}),
		});

		expect(result.source).toBe("project virtual environment");
	});

	test("explains how to create a compatible environment", async () => {
		await expect(
			discoverPythonRuntime({
				workspaceDirectory: "C:/project",
				candidates,
				probe: probe({
					"configured-python": { executable: "C:/Python310/python.exe", major: 3, minor: 10, hasPydantic: true },
					"venv-python": {
						executable: "C:/project/python/.venv/python.exe",
						major: 3,
						minor: 12,
						hasPydantic: false,
					},
				}),
			}),
		).rejects.toThrow(PythonRuntimeDiscoveryError);
	});
});
