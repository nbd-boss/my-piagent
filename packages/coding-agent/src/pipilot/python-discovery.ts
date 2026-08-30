import { execFile } from "node:child_process";
import { existsSync } from "node:fs";
import { delimiter, join } from "node:path";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const MINIMUM_PYTHON_MAJOR = 3;
const MINIMUM_PYTHON_MINOR = 11;

export interface PythonRuntimeCandidate {
	command: string;
	args: readonly string[];
	label: string;
}

export interface PythonRuntimeProbeResult {
	executable: string;
	major: number;
	minor: number;
	hasPydantic: boolean;
}

export type PythonRuntimeProbe = (candidate: PythonRuntimeCandidate) => Promise<PythonRuntimeProbeResult | undefined>;

export interface PythonRuntimeDiscoveryOptions {
	workspaceDirectory: string;
	pythonPath?: string;
	candidates?: readonly PythonRuntimeCandidate[];
	probe?: PythonRuntimeProbe;
}

export interface PythonRuntimeDiscovery {
	pythonPath: string;
	version: `${number}.${number}`;
	source: string;
}

export class PythonRuntimeDiscoveryError extends Error {
	constructor(message: string) {
		super(message);
		this.name = "PythonRuntimeDiscoveryError";
	}
}

const probeScript = [
	"import importlib.util, json, sys",
	'print(json.dumps({"executable": sys.executable, "major": sys.version_info.major, "minor": sys.version_info.minor, "hasPydantic": importlib.util.find_spec("pydantic") is not None}))',
].join("; ");

function defaultCandidates(options: PythonRuntimeDiscoveryOptions): PythonRuntimeCandidate[] {
	const virtualEnvironmentPython = join(
		options.workspaceDirectory,
		"python",
		".venv",
		process.platform === "win32" ? "Scripts" : "bin",
		process.platform === "win32" ? "python.exe" : "python",
	);
	const candidates: PythonRuntimeCandidate[] = [];

	if (options.pythonPath) {
		candidates.push({ command: options.pythonPath, args: [], label: "configured Python" });
	}
	if (existsSync(virtualEnvironmentPython)) {
		candidates.push({ command: virtualEnvironmentPython, args: [], label: "project virtual environment" });
	}
	if (!options.pythonPath) {
		candidates.push(
			{ command: "py", args: ["-3.12"], label: "Python Launcher 3.12" },
			{ command: "py", args: ["-3.11"], label: "Python Launcher 3.11" },
			{ command: "python", args: [], label: "system Python" },
		);
	}

	return candidates;
}

function parseProbeResult(value: unknown): PythonRuntimeProbeResult | undefined {
	if (typeof value !== "object" || value === null || Array.isArray(value)) return undefined;
	const record = value as Record<string, unknown>;
	if (
		typeof record.executable !== "string" ||
		typeof record.major !== "number" ||
		typeof record.minor !== "number" ||
		typeof record.hasPydantic !== "boolean"
	) {
		return undefined;
	}
	return {
		executable: record.executable,
		major: record.major,
		minor: record.minor,
		hasPydantic: record.hasPydantic,
	};
}

async function probePythonRuntime(candidate: PythonRuntimeCandidate): Promise<PythonRuntimeProbeResult | undefined> {
	try {
		const { stdout } = await execFileAsync(candidate.command, [...candidate.args, "-c", probeScript], {
			encoding: "utf8",
			env: process.env,
		});
		return parseProbeResult(JSON.parse(stdout.trim()) as unknown);
	} catch {
		return undefined;
	}
}

function supportsMinimumVersion(result: PythonRuntimeProbeResult): boolean {
	return (
		result.major > MINIMUM_PYTHON_MAJOR ||
		(result.major === MINIMUM_PYTHON_MAJOR && result.minor >= MINIMUM_PYTHON_MINOR)
	);
}

export async function discoverPythonRuntime(options: PythonRuntimeDiscoveryOptions): Promise<PythonRuntimeDiscovery> {
	const candidates = options.candidates ?? defaultCandidates(options);
	const probe = options.probe ?? probePythonRuntime;
	const failures: string[] = [];

	for (const candidate of candidates) {
		const result = await probe(candidate);
		if (!result) {
			failures.push(`${candidate.label} could not be started`);
			continue;
		}
		if (!supportsMinimumVersion(result)) {
			failures.push(
				`${candidate.label} is Python ${result.major}.${result.minor}; Python 3.11 or newer is required`,
			);
			continue;
		}
		if (!result.hasPydantic) {
			failures.push(`${candidate.label} is missing PiCode dependencies`);
			continue;
		}

		return {
			pythonPath: result.executable,
			version: `${result.major}.${result.minor}`,
			source: candidate.label,
		};
	}

	const command = process.platform === "win32" ? "py -3.12 -m venv python\\.venv" : "python3.12 -m venv python/.venv";
	const install =
		process.platform === "win32"
			? 'python\\.venv\\Scripts\\python.exe -m pip install -e "python[dev]"'
			: 'python/.venv/bin/python -m pip install -e "python[dev]"';
	throw new PythonRuntimeDiscoveryError(
		[
			"No compatible Python Runtime was found.",
			...failures,
			`Create and install it with: ${command} && ${install}`,
		].join(`${delimiter === ";" ? "\r\n" : "\n"}`),
	);
}
