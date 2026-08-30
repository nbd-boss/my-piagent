# PiCode：面向真实研发任务的 Coding Agent Runtime

PiCode 基于 pi 的终端 TUI 构建，但将 Agent 决策放在独立 Python Runtime 中。目标不是重做一个聊天式 CLI，而是验证 Coding Agent 在真实仓库中的几个工程问题：请求如何路由、何时进入长任务、如何安全调用工具，以及如何解释决策过程。

## 1. 交互入口：自然语言，而不是预设工作流

用户只需在 TUI 输入自然语言；系统不会把每条消息都当作“立即修改代码”的长任务。Router 先输出最小决策：`intent`、`executionClass` 和必要时的澄清问题。

例如：

```text
输入：解释认证流程在哪里。
输出：inspect + high_frequency

输入：修复登录接口空邮箱导致 500 的问题，并补测试。
输出：change + long_task_agent
```

这对应 AI IDE 中高频代码理解与长时间修改任务的差异化架构：前者追求低延迟、小上下文和只读工具；后者才需要计划、状态、工具预算和验证。

## 2. 澄清不是失败：同一任务内重新路由

对于“帮我处理认证问题”这种信息不足的输入，Runtime 返回具体问题，不猜测、不申请写权限，也不创建正式任务：

```text
Agent：你希望我先定位认证问题，还是修改代码并补测试？
用户：先定位认证流程，不要修改代码。
Agent：inspect + high_frequency
```

补充信息通过同一 `taskId` 的 `steer` 消息回到 Runtime，再与原始请求合并后重新路由。这样既保留对话上下文，也避免把一次澄清误记为失败任务；连续两次仍不明确才安全结束。

## 3. 运行时边界：Python Agent Runtime + TypeScript Host

Python 负责路由、任务状态和后续 Agent 决策；TypeScript 复用 pi 的 TUI 与现有代码工具，作为工具和界面宿主。两端不共享进程内状态，而是经 stdin/stdout JSONL 通信。

每条协议消息有 `protocolVersion`、`taskId`、`requestId` 和事件类型。Python 使用 Pydantic，TypeScript 使用运行时解析校验同一份语义：未知协议版本、非法 JSON、异常退出和不合法路由结果都有明确错误。

这个设计的价值是将 Agent Runtime 从 TUI 解耦：同一 Runtime 后续可以被终端、print mode 或 RPC 调用，而不复制 Agent Loop。

## 4. 安全边界：执行架构升级不等于获得写权限

PiCode 将“选择长任务执行架构”和“允许修改仓库”分开。

例如，用户先让 Agent 阅读 CI 日志。即使后续发现问题横跨多个模块，需要升级为 `long_task_agent`，Runtime 也只能增加计划、记忆和工具预算；权限仍保持 `read-only`。真正要 edit/write 时，才由 TypeScript Tool Host 做最终工作区与权限校验，并请求 `workspace-write`。

这避免了“模型认为要修复”直接变成“模型可以写文件”的权限穿透问题。

## 5. 工具 Schema 与普通 Context 分离

PiCode 不在 Prompt 中手写或复制工具说明。TypeScript ToolRegistry 是工具 JSON Schema 的唯一来源；任务启动时，Tool Host 将当前启用工具的名称、说明和参数 Schema 同步给 Python Runtime。Python 调用模型时将它们放入模型 API 的 `tools` 参数，而不是交给 ContextEngine 拼入普通文本上下文。

例如，用户说“读取 `package.json` 并告诉我 scripts”：模型从 `read` 工具的 JSON Schema 中生成结构化调用；Python 将调用转为 `tool_request`；Tool Host 执行后回传结果。若用户接着要求修改 scripts，模型可以请求写工具，但 Tool Host 仍会在执行时发起审批。模型知道工具形状，不拥有工具权限。

这样避免两套工具定义漂移，也不会让长 Schema 挤占 `AGENTS.md`、环境事实和用户任务的上下文空间。

## 6. Router 的工程化设计

Router 的正式路径采用“模型主路由 + 结构化校验 + 独立安全约束”：

- 当前模型输出 `RouteDecision`，不维护一套会持续膨胀的关键词意图分类器；
- 模型输出必须通过 `RouteDecision` 校验，不合法就回到澄清，而不是被当作可执行指令；
- “不修改代码”、push、deploy、删除等安全约束不依赖模型判断，分别由权限策略和 Tool Host 强制执行；
- 开发和离线测试可以注入确定性 mock classifier，保证测试不消耗模型额度。

高频问答后续可让首轮模型同时产出路由和回答，避免为了分类额外增加一次模型往返。

## 7. 当前实现与下一步

已完成：跨语言 JSONL 协议、Python 子进程管理、解释器发现、路由数据模型、澄清状态机、同任务 steering、路由契约测试。当前确定性 classifier 仅作开发期 mock。

下一步：实现 `ExecutionPolicy` 和运行中升级、权限管理与 TypeScript Tool Host、上下文构建、动态计划、验证合同、Trace/Eval。重点不是堆功能，而是用 Trace 和可重复任务评估路由、上下文和恢复策略是否真的提升成功率、延迟和成本。
