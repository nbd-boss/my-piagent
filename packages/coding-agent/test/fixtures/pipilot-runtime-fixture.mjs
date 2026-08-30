import { createInterface } from "node:readline";

function emit(message) {
	process.stdout.write(`${JSON.stringify(message)}\n`);
}

const input = createInterface({ input: process.stdin, crlfDelay: Infinity });

for await (const line of input) {
	const message = JSON.parse(line);
	if (message.type === "host_hello") {
		emit({
			protocolVersion: 1,
			taskId: message.taskId,
			requestId: message.requestId,
			type: "runtime_ready",
			capabilities: ["fixture"],
		});
	} else if (message.type === "user_message") {
		emit({
			protocolVersion: 1,
			taskId: message.taskId,
			requestId: message.requestId,
			type: "assistant_delta",
			delta: `fixture:${message.content}`,
		});
		emit({
			protocolVersion: 1,
			taskId: message.taskId,
			requestId: message.requestId,
			type: "task_finished",
			status: "success",
			summary: "fixture complete",
		});
	} else if (message.type === "steer") {
		emit({
			protocolVersion: 1,
			taskId: message.taskId,
			requestId: message.requestId,
			type: "assistant_delta",
			delta: `fixture:steer:${message.content}`,
		});
	} else if (message.type === "cancel") {
		emit({
			protocolVersion: 1,
			taskId: message.taskId,
			requestId: message.requestId,
			type: "task_finished",
			status: "cancelled",
			summary: message.reason ?? "cancelled",
		});
	} else if (message.type === "task_status") {
		emit({
			protocolVersion: 1,
			taskId: message.taskId,
			requestId: message.requestId,
			type: "task_state",
			found: false,
		});
	}
}
