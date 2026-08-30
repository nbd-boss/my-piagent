import { type ChildProcess, spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import { delimiter } from "node:path";
import type { Readable, Writable } from "node:stream";
import { attachJsonlLineReader } from "../modes/rpc/jsonl.ts";
import {
	type HostMessage,
	PIPILOT_PROTOCOL_VERSION,
	parseRuntimeMessage,
	type RuntimeMessage,
	type RuntimeReady,
	serializeHostMessage,
} from "./protocol.ts";
import { discoverPythonRuntime } from "./python-discovery.ts";

export interface RuntimeLaunchOptions {
	command: string;
	args: readonly string[];
	cwd?: string;
	environment?: NodeJS.ProcessEnv;
	startupTimeoutMs?: number;
}

export interface PythonRuntimeLaunchOptions {
	pythonPath: string;
	moduleName?: string;
	sourcePath?: string;
	cwd?: string;
	environment?: NodeJS.ProcessEnv;
}

export interface StartPythonRuntimeOptions extends Omit<PythonRuntimeLaunchOptions, "pythonPath" | "cwd"> {
	workspaceDirectory: string;
	pythonPath?: string;
	cwd?: string;
}

export interface RuntimeClientDiagnostic {
	code: "invalid_runtime_message" | "process_error" | "process_exit";
	message: string;
	stderr: string;
}

export type RuntimeMessageListener = (message: RuntimeMessage) => void;
export type RuntimeDiagnosticListener = (diagnostic: RuntimeClientDiagnostic) => void;

export function createPythonRuntimeLaunch(options: PythonRuntimeLaunchOptions): RuntimeLaunchOptions {
	const pythonPathEntries = [options.sourcePath, options.environment?.PYTHONPATH, process.env.PYTHONPATH].filter(
		(value): value is string => value !== undefined && value !== "",
	);

	return {
		command: options.pythonPath,
		args: ["-m", options.moduleName ?? "pipilot_runtime"],
		cwd: options.cwd,
		environment: {
			...options.environment,
			...(pythonPathEntries.length > 0 ? { PYTHONPATH: pythonPathEntries.join(delimiter) } : {}),
		},
	};
}

export async function startPythonRuntime(options: StartPythonRuntimeOptions): Promise<RuntimeClient> {
	const runtime = await discoverPythonRuntime({
		workspaceDirectory: options.workspaceDirectory,
		pythonPath: options.pythonPath,
	});
	return RuntimeClient.start(
		createPythonRuntimeLaunch({
			pythonPath: runtime.pythonPath,
			moduleName: options.moduleName,
			sourcePath: options.sourcePath,
			cwd: options.cwd ?? options.workspaceDirectory,
			environment: options.environment,
		}),
	);
}

export class RuntimeClient {
	readonly #process: ChildProcess;
	readonly #stdin: Writable;
	readonly #stdout: Readable;
	readonly #stderr: Readable;
	readonly #messageListeners = new Set<RuntimeMessageListener>();
	readonly #diagnosticListeners = new Set<RuntimeDiagnosticListener>();
	readonly #stderrChunks: string[] = [];
	readonly #readyPromise: Promise<RuntimeReady>;
	#resolveReady: (message: RuntimeReady) => void = () => {};
	#rejectReady: (error: Error) => void = () => {};
	#readySettled = false;
	#closed = false;
	#detachLineReader: (() => void) | undefined;

	private constructor(process: ChildProcess, stdin: Writable, stdout: Readable, stderr: Readable) {
		this.#process = process;
		this.#stdin = stdin;
		this.#stdout = stdout;
		this.#stderr = stderr;
		this.#readyPromise = new Promise<RuntimeReady>((resolve, reject) => {
			this.#resolveReady = resolve;
			this.#rejectReady = reject;
		});

		this.#detachLineReader = attachJsonlLineReader(this.#stdout, (line) => this.#handleLine(line));
		this.#stderr.setEncoding("utf8");
		this.#stderr.on("data", (chunk: string) => this.#stderrChunks.push(chunk));
		this.#process.on("error", (error) => this.#handleProcessError(error));
		this.#process.on("exit", (code, signal) => this.#handleProcessExit(code, signal));
	}

	static async start(options: RuntimeLaunchOptions): Promise<RuntimeClient> {
		const process = spawn(options.command, options.args, {
			cwd: options.cwd,
			env: { ...globalThis.process.env, ...options.environment },
			stdio: "pipe",
		});
		const stdin = process.stdin;
		const stdout = process.stdout;
		const stderr = process.stderr;
		if (!stdin || !stdout || !stderr) {
			process.kill();
			throw new Error("Failed to create Python Runtime stdio streams");
		}

		const client = new RuntimeClient(process, stdin, stdout, stderr);
		try {
			client.#send({
				protocolVersion: PIPILOT_PROTOCOL_VERSION,
				taskId: "runtime",
				requestId: randomUUID(),
				type: "host_hello",
			});
			await client.#waitForReady(options.startupTimeoutMs ?? 5_000);
			return client;
		} catch (error) {
			client.dispose();
			throw error;
		}
	}

	subscribe(listener: RuntimeMessageListener): () => void {
		this.#messageListeners.add(listener);
		return () => this.#messageListeners.delete(listener);
	}

	subscribeDiagnostics(listener: RuntimeDiagnosticListener): () => void {
		this.#diagnosticListeners.add(listener);
		return () => this.#diagnosticListeners.delete(listener);
	}

	sendUserMessage(taskId: string, content: string): string {
		const requestId = randomUUID();
		this.#send({ protocolVersion: PIPILOT_PROTOCOL_VERSION, taskId, requestId, type: "user_message", content });
		return requestId;
	}

	steer(taskId: string, content: string): string {
		const requestId = randomUUID();
		this.#send({ protocolVersion: PIPILOT_PROTOCOL_VERSION, taskId, requestId, type: "steer", content });
		return requestId;
	}

	respondToPermission(taskId: string, granted: boolean): string {
		const requestId = randomUUID();
		this.#send({
			protocolVersion: PIPILOT_PROTOCOL_VERSION,
			taskId,
			requestId,
			type: "permission_response",
			granted,
		});
		return requestId;
	}

	cancel(taskId: string, reason?: string): string {
		const requestId = randomUUID();
		this.#send({ protocolVersion: PIPILOT_PROTOCOL_VERSION, taskId, requestId, type: "cancel", reason });
		return requestId;
	}

	getTaskStatus(taskId: string): string {
		const requestId = randomUUID();
		this.#send({ protocolVersion: PIPILOT_PROTOCOL_VERSION, taskId, requestId, type: "task_status" });
		return requestId;
	}

	dispose(): void {
		if (this.#closed) return;
		this.#closed = true;
		this.#detachLineReader?.();
		this.#stdin.end();
		if (!this.#process.killed) {
			this.#process.kill();
		}
	}

	#getStderr(): string {
		return this.#stderrChunks.join("");
	}

	#send(message: HostMessage): void {
		if (this.#closed || !this.#stdin.writable) {
			throw new Error("Python Runtime is not running");
		}
		this.#stdin.write(serializeHostMessage(message));
	}

	async #waitForReady(timeoutMs: number): Promise<RuntimeReady> {
		let timeout: NodeJS.Timeout | undefined;
		const timeoutPromise = new Promise<never>((_, reject) => {
			timeout = setTimeout(
				() => reject(new Error(`Python Runtime did not complete handshake within ${timeoutMs}ms`)),
				timeoutMs,
			);
		});

		try {
			return await Promise.race([this.#readyPromise, timeoutPromise]);
		} finally {
			if (timeout) clearTimeout(timeout);
		}
	}

	#handleLine(line: string): void {
		try {
			const message = parseRuntimeMessage(JSON.parse(line) as unknown);
			if (message.type === "runtime_ready" && !this.#readySettled) {
				this.#readySettled = true;
				this.#resolveReady(message);
			}
			for (const listener of this.#messageListeners) {
				listener(message);
			}
		} catch (error) {
			const message = error instanceof Error ? error.message : String(error);
			this.#emitDiagnostic({ code: "invalid_runtime_message", message, stderr: this.#getStderr() });
			if (!this.#readySettled) {
				this.#readySettled = true;
				this.#rejectReady(new Error(message));
			}
		}
	}

	#handleProcessError(error: Error): void {
		this.#emitDiagnostic({ code: "process_error", message: error.message, stderr: this.#getStderr() });
		if (!this.#readySettled) {
			this.#readySettled = true;
			this.#rejectReady(error);
		}
	}

	#handleProcessExit(code: number | null, signal: NodeJS.Signals | null): void {
		const message = `Python Runtime exited with code ${String(code)} and signal ${String(signal)}`;
		this.#emitDiagnostic({ code: "process_exit", message, stderr: this.#getStderr() });
		if (!this.#readySettled) {
			this.#readySettled = true;
			this.#rejectReady(new Error(message));
		}
	}

	#emitDiagnostic(diagnostic: RuntimeClientDiagnostic): void {
		for (const listener of this.#diagnosticListeners) {
			listener(diagnostic);
		}
	}
}
