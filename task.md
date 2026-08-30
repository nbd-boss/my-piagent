# PiCode 开发任务计划

## 1. 文档用途

本文将 [spec.md](./spec.md) 转换为可执行任务。每一节对应一项 Runtime 能力，并包含目标、默认实现、任务和验收标准。

最终技术边界：

- Python 实现唯一的 PiCode Runtime。
- Agent Loop、状态、工具调度、权限、Context、恢复、验证和 Trace 均由 PiCode 实现。
- LangChain 仅用于模型、消息、流式 tool call 和结构化输出适配。
- 不使用 LangGraph、Deep Agents、`create_agent` 或 `AgentExecutor`。
- TUI 使用 Python 实现，不再把 TypeScript Host 作为核心依赖。
- 先完成可运行的最小链路，再处理旧 TS/Python bridge。

任务状态：

- `[ ]`：未完成；
- `[x]`：已经实现并通过对应验证。

---

## 2. 目标目录与依赖

目标目录：

```text
python/
  pyproject.toml
  src/picode/
    __main__.py
    cli.py
    config.py
    events.py
    types.py
    runtime/
      agent_loop.py
      state.py
      controller.py
      execution_policy.py
    routing/
      models.py
      prompt.py
      router.py
    models/
      gateway.py
      langchain_adapter.py
      catalog.py
    context/
      engine.py
      project_rules.py
      user_task.py
      compaction.py
    tools/
      registry.py
      runtime.py
      permission.py
      read.py
      search.py
      edit.py
      shell.py
    memory/
      task_memory.py
      snapshot.py
      store.py
    planning/
      models.py
      planner.py
    verification/
      contract.py
      verifier.py
    recovery/
      classifier.py
      policy.py
    trace/
      events.py
      collector.py
      writer.py
    eval/
      dataset.py
      runner.py
    tui/
      app.py
      views/
  tests/
```

目录只在职责形成后创建，不为占位而拆文件。当前 `python/src/pipilot_runtime` 在迁移完成前保留；新 Runtime 最小链路稳定后，再将可复用模块迁入 `picode`。

最低 Python 3.11，推荐 3.12。依赖通过 `pyproject.toml` 固定版本：

- `langchain-core`：消息与模型抽象；
- `langchain-openai`：DeepSeek/OpenAI-compatible 接入；
- Pydantic：结构化类型；
- Textual、Typer：TUI 和 CLI；
- SQLite 标准库：任务快照；
- pytest、Ruff、Pyright：验证。

不安装完整 `langchain` 元包，除非后续出现无法由 core 包解决的明确需求。

---

## 3. 架构迁移与现有资产

### 目标

从“pi TypeScript Host + JSONL + Python Runtime”迁移到单进程 Python Runtime，同时保留已经完成的有效实现。

### 当前资产

| 能力 | 当前状态 | 迁移处理 |
| --- | --- | --- |
| Python 项目、解释器发现和测试基础 | 已完成 | 直接保留 |
| Intent Router、澄清和 DeepSeek 路由 | 已完成 | 接入新 Runtime |
| Permission 状态与失败重复保护 | 已完成 | 保留领域逻辑，移除 TS 依赖 |
| `AGENTS.md`、`UserTask` 初始 Context | 已完成 | 直接保留 |
| Round、ToolCallRecord、TaskCheckpoint | 已完成 | 接入 Agent Loop |
| Trace JSONL、脱敏和 Context 投影 | 已完成 | 接入 Runtime Event |
| TypeScript Tool Host、PermissionManager | 已完成的旧实验 | 冻结，仅作参考 |
| JSONL 子进程协议 | 已完成的旧实验 | 不再扩展 |

### 任务

- [x] 建立 Python 3.11+ 项目、虚拟环境、Ruff、Pyright 和 pytest。
- [x] 完成旧版 Python/TypeScript JSONL 契约实验。
- [x] 识别可迁移的 Router、Context、Permission、Memory 和 Trace 模块。
- [ ] 在 `pyproject.toml` 中加入并固定 LangChain core/model 依赖。
- [ ] 建立 `picode` 包和 CLI 入口，但暂不移动全部旧代码。
- [ ] 用一个 mock model 完成“用户消息 → 模型文本 → Runtime Event”最小链路。
- [ ] 用 DeepSeek 完成“用户消息 → 一个只读工具 → 工具结果 → 最终回复”真实链路。
- [ ] 最小链路通过后，将可复用 Python 模块迁入 `picode` 并更新导入。
- [ ] 迁移完成后单独评估旧 TypeScript 文件；未经确认不删除。

### 验收

- 核心链路在无 Node.js、无 TypeScript Host 的情况下运行。
- 旧实现和新实现不会同时成为权威任务状态来源。
- 迁移前已完成的 Python 单元测试继续通过。
- DeepSeek 实测只通过显式命令运行，不默认消耗额度。

---

## 4. Runtime 状态与事件

### 目标

定义 Agent Loop 读写的唯一状态，以及 TUI、Trace 和测试共同消费的事件。

### 默认实现

`RuntimeState` 是当前任务的权威内存状态，至少包含：

- `taskId`、状态和执行策略；
- `UserTask`、路由结果和追加约束；
- 模型消息或消息引用；
- 当前目标、计划和未完成事项；
- 权限状态与 `PendingAction`；
- 工具结果、修改文件和验证结果；
- 预算、取消状态和最近 Checkpoint。

`RuntimeEvent` 是追加式事实，不允许 TUI 反向修改。首版事件包括：

```text
task_started
route_decided
assistant_delta
round_started
tool_started
permission_required
tool_finished
plan_updated
verification_updated
task_paused
task_finished
```

### 任务

- [x] 定义现有任务 ID、路由、取消和查询基础类型。
- [ ] 定义不依赖 LangChain 和 TUI 类型的 `RuntimeState`。
- [ ] 定义版本化 `RuntimeEvent` 联合类型。
- [ ] 实现仅允许合法状态迁移的状态机。
- [ ] 实现进程内异步事件订阅。
- [ ] 定义 `PendingAction`，保存等待权限或用户输入的动作。
- [ ] 定义取消在模型流、工具执行和等待用户三个阶段的语义。
- [ ] 为事件顺序、非法状态迁移和取消编写测试。

### 验收

- Runtime 可在无 TUI 环境下运行和测试。
- TUI 只能发送用户输入、权限响应、steering 和取消，不能直接改状态。
- 取消后不会产生新的写入工具调用。
- Runtime State 中不保存密钥和完整大输出。

---

## 5. 意图识别与执行策略选择

### 目标

从自然语言中识别任务意图、执行策略以及是否需要澄清。

### 输入与输出

输入：

```json
{
  "userMessage": "修复登录接口空邮箱导致 500 的问题，并补一个测试。"
}
```

输出：

```json
{
  "intent": "change",
  "executionClass": "long_task_agent",
  "clarificationQuestion": null,
  "reason": "请求要求修改代码并补测试。"
}
```

信息不足时：

```json
{
  "intent": "ambiguous",
  "executionClass": null,
  "clarificationQuestion": "你希望我先定位认证问题，还是修改代码并补测试？"
}
```

### 默认实现

Router 使用结构化模型输出，Pydantic 负责校验。关键词规则不作为产品主路径；mock classifier 仅用于确定性测试。Router 不预测权限和具体工具。

### 任务

- [x] 定义 Router 输入、输出和 Pydantic 校验。
- [x] 实现 mock classifier 和中英文路由样例。
- [x] 实现 ModelRouteClassifier 和结构化输出回退。
- [x] 接入 DeepSeek Router Provider 和缺失密钥提示。
- [x] 实现同一任务内的澄清与 steer 重新路由。
- [ ] 将现有 Router 改接 `ModelGateway`，不直接依赖旧 Provider。
- [ ] 将路由结果写入 `RuntimeState` 和 `RuntimeEvent`。
- [ ] 支持执行过程中从 `high_frequency` 升级到 `long_task_agent`。
- [ ] 验证策略升级不会修改权限状态。

### 验收

- 不明确的请求先返回澄清问题，不启动工具执行。
- Router 输出非法时不会进入 Agent Loop。
- 普通用户不需要手动选择模式。
- 执行策略和工具权限保持独立。

---

## 6. 自研 Agent Loop

### 目标

实现模型驱动的“准备 Context → 调用模型 → 执行工具 → 回填结果 → 再决策”循环。

### 默认实现

LangChain 只返回统一的模型消息。循环由 `AgentLoop` 控制：

```text
prepare
  → model
  → final response ─────────────→ verify/finalize
  → tool calls
       → permission check
       → execute
       → observe
       └────────────────────────→ prepare
```

一轮由一次模型响应和其产生的工具调用结果组成。模型决定工具和下一步，Runtime 决定预算、权限、状态和结束条件。

### 简单例子

用户输入“修复空邮箱导致的 500，并补测试”：

1. 模型调用 `search`；
2. Runtime 执行并回填匹配位置；
3. 模型调用 `read`；
4. 模型请求 `edit`，Runtime 暂停等待写权限；
5. 用户允许后继续执行编辑；
6. 模型调用 `shell` 运行相关测试；
7. Runtime 根据验证结果决定继续修复或结束。

这不是固定 workflow，因为模型可以选择不同文件、工具顺序和重规划方式。

### 任务

- [ ] 定义 `AgentLoopConfig`：模型、工具、预算、超时和执行策略。
- [ ] 实现模型流式事件到 `RuntimeEvent` 的转换。
- [ ] 解析零个、一个或多个 tool call，并保持 call ID 对应。
- [ ] 将工具结果转换为 `ToolMessage` 后继续下一轮。
- [ ] 将每轮目标、动作和结果写入现有 `ExecutionLedger`。
- [ ] 实现最大轮数、模型调用数、工具调用数和时间预算。
- [ ] 实现等待权限、steering、取消和继续。
- [ ] 实现进入验证、完成、阻塞和失败的确定性出口。
- [ ] 为文本回答、单工具、多工具、工具失败、取消和超预算编写 mock 测试。

### 验收

- Agent 能完成至少三轮“模型—工具—结果”交互。
- Tool call ID 和 ToolMessage 不会错配。
- 相同失败不会无限循环。
- TUI 关闭不会留下继续写入的后台任务。
- Agent Loop 不依赖 Textual、SQLite 或具体模型 Provider。

---

## 7. 模型与 Prompt 策略

### 目标

用统一接口接入模型，同时保留 PiCode 对流式事件、路由、失败和成本的控制。

### LangChain 使用边界

使用：

- `BaseChatModel`；
- `SystemMessage`、`HumanMessage`、`AIMessage`、`ToolMessage`；
- `bind_tools()`；
- `with_structured_output()`；
- `ChatOpenAI` 和后续需要的具体 Provider。

不使用：

- LangChain Agent、Memory 或 AgentExecutor；
- LangGraph；
- 框架提供的任务状态、工具执行或重试策略。

### 默认实现

`ModelGateway` 对 Runtime 暴露自己的类型：

```text
ModelRequest → AsyncIterator[ModelEvent] → ModelResult
```

`LangChainModelAdapter` 在边界处完成 PiCode 类型和 LangChain 消息之间的转换。首版用 `ChatOpenAI(base_url=...)` 接入 DeepSeek。

### 任务

- [x] 已有 DeepSeek OpenAI-compatible Provider 和 mock provider。
- [x] 已有 Router Prompt 和结构化输出校验。
- [ ] 定义 `ModelRequest`、`ModelEvent`、`ModelResult` 和错误类型。
- [ ] 实现 `LangChainModelAdapter`。
- [ ] 接入 DeepSeek 文本流、tool call、finish reason 和 usage。
- [ ] 校验流式工具参数的合并与错误处理。
- [ ] 定义 Agent Prompt 模板和版本。
- [ ] 区分项目规则、用户任务、执行状态和动态 Context。
- [ ] 实现超时、限流、无效响应和 Provider 不可用分类。
- [ ] 统计首 token 延迟、输入/输出 token、缓存和费用。
- [ ] 实现模型目录和用户手动选择。
- [ ] 后续增加第二个 Provider，验证 Agent Loop 无需修改。

### 验收

- LangChain 类型不会进入 `RuntimeState` 和 SQLite。
- 切换 Provider 不需要修改 Agent Loop。
- 用户指定模型时不会被自动路由静默覆盖。
- API Key 不进入消息、事件、Trace 或快照。

---

## 8. Context 管理

### 8.1 初始 Context

#### 目标

在首次模型调用前构建最小且可追溯的 Context。

#### 默认实现

只包含：

1. 从仓库根目录到当前工作目录合并的 `AGENTS.md`；
2. `UserTask`：原始请求、追加约束和 Host 提供的执行范围。

工具 JSON Schema 通过 `bind_tools()` 单独传递，不重复写入 Prompt。

#### 任务

- [x] 定义初始 Context 类型和序列化顺序。
- [x] 实现 `AGENTS.md` 读取、合并和来源记录。
- [x] 分开保存用户原文、追加约束和 Host 执行范围。
- [x] 实现 `build_initial_context()` 和测试。
- [ ] 将输出转换为 Model Gateway 所需的统一消息。

#### 验收

- 每块初始 Context 都能追溯来源。
- 不自动加入整仓库代码、完整工具输出或历史任务。

### 8.2 执行过程中的关键信息

#### 目标

保存每轮目标、动作、结果和工具证据，同时只把必要信息送入下一轮模型调用。

#### 默认实现

沿用现有：

- `ReActRound`：目标、动作和结果；
- `ToolCallRecord`：工具、参数指纹、状态、耗时、退出码、摘要和输出引用；
- `TaskCheckpoint`：阶段事实、状态和下一目标；
- Trace 事件：`thinking`、`tool_call`、`tool_result`、`checkpoint`。

`thinking` 只保存模型公开返回的决策摘要，不记录隐藏思维链。

#### 任务

- [x] 定义 Round、ToolCallRecord 和 TaskCheckpoint。
- [x] 定义追加式 Trace 事件并实现脱敏。
- [x] 实现执行 Context 投影。
- [ ] 由 Agent Loop 自动创建和完成 Round。
- [ ] 由 Python Tool Runtime 自动记录 tool call/result。
- [ ] 将最近结果、Checkpoint、未完成事项和必要证据加入下一轮 Context。
- [ ] 为 `/context` 提供来源和已省略内容摘要。

#### 验收

- 下一轮能够知道当前目标、最近结果和未完成事项。
- 完整大输出和完整可见推理不会反复进入 Prompt。
- Trace 可以按顺序回放公开的执行过程。

### 8.3 压缩与失效

#### 目标

控制长任务上下文，同时保留恢复需要的事实和证据。

#### 任务

- [ ] 定义触发条件：上下文窗口、阶段完成或长输出。
- [ ] 定义压缩结果必须保留的目标、约束、事实、证据、修改和未完成事项。
- [ ] 对已经失效的事实和失败假设做显式标记。
- [ ] 定义 Context Snapshot 与 TaskMemory 的边界。
- [ ] 用 Eval 比较压缩前后的成功率、延迟和 token。

#### 验收

- 压缩后仍能说明做了什么、为什么、验证结果和下一步。
- 原始大输出只保留引用。
- 恢复后不会因摘要缺失而重复高风险操作。

---

## 9. 任务记忆与持久化

### 目标

让任务在多轮执行和进程中断后保留目标、约束、证据和等待状态。

### 默认实现

`TaskMemory` 保存业务状态；`RuntimeSnapshot` 保存循环恢复状态：

- TaskMemory：目标、约束、计划、事实、修改、验证和未完成事项；
- RuntimeSnapshot：循环位置、消息引用、PendingAction、预算和取消状态。

Phase 1 使用内存，Phase 2 使用 SQLite。恢复任务时权限重置为只读。

### 任务

- [x] 定义可序列化的 TaskMemory 基础类型。
- [ ] 实现目标和约束只追加、不静默覆盖。
- [ ] 实现计划版本和合法状态迁移。
- [ ] 定义版本化 RuntimeSnapshot。
- [ ] 将消息大对象和工具大输出改为引用。
- [ ] 实现 SQLite 原子保存、读取和损坏检查。
- [ ] 定义快照时机：计划确定、steering、修改、验证、等待和退出。
- [ ] 恢复时比较仓库根目录、Git HEAD、工作区和关键文件哈希。
- [ ] 实现任务列表、暂停、恢复和取消。
- [ ] 记录外部副作用指纹，恢复时不自动重复。

### 验收

- 目标和用户约束不会被后续摘要覆盖。
- 等待权限时退出进程可以恢复到相同 PendingAction。
- 恢复任务不会继承写权限。
- 工作区变化不会被静默覆盖。

---

## 10. Python Tool Runtime 与权限

### 目标

在 Python 中提供可审计、受权限约束的代码工具，不依赖 pi Tool Host。

### 默认实现

首版工具：

- `read`：读取工作区文件；
- `search`：按路径和文本搜索；
- `edit`：应用明确的文件修改；
- `shell`：运行测试、构建和必要命令。

`ToolRegistry` 保存工具 Schema、权限等级和执行函数；`ToolRuntime` 统一处理参数校验、路径限制、超时、取消、输出截断、Trace 和错误分类。

### 任务

- [x] 已有任务级权限状态和拒绝/取消逻辑。
- [x] 已有路径策略、风险分类和重复失败保护实验。
- [x] 已有 TypeScript Tool Host 行为测试，作为迁移参考。
- [ ] 定义 Python `ToolDefinition`、`ToolRequest` 和 `ToolResult`。
- [ ] 实现 ToolRegistry 和 LangChain tool Schema 转换。
- [ ] 实现工作区路径解析和越界拒绝。
- [ ] 实现 read、search、edit 和 shell。
- [ ] 实现修改前基线哈希检查，避免覆盖并发改动。
- [ ] 实现超时、取消、输出上限和原始输出引用。
- [ ] 实现 Shell 风险分类；无法判断时要求确认。
- [ ] 将权限请求保存为 PendingAction 并通过 Runtime Event 暴露。
- [ ] 用户允许、拒绝或编辑参数后继续同一 Agent Loop。
- [ ] 为只读、写入、越界、高风险、超时和取消编写测试。

### 验收

- 只读工具不会弹出权限确认。
- 未授权 edit 和写入型 shell 不会执行。
- 工作区写权限不能执行 push、deploy 或大范围删除。
- 工具调用具有成对的开始和结束事件。
- Windows 路径和 PowerShell 命令具有专门测试。

---

## 11. 两类执行策略与动态计划

### 目标

使用一个 Agent Loop，为高频请求和长任务配置不同资源策略，并让长任务计划可随证据更新。

### 默认实现

- `high_frequency`：小 Context、较低模型预算、只读工具、不创建长计划；
- `long_task_agent`：动态 Context、任务记忆、计划、更多工具轮次和 Verification Contract。

计划由模型维护，不是 Runtime 固定工作流。用户原始要求先标准化为 `Requirement`，再映射到 `PlanStep`。

### 任务

- [ ] 定义两类 ExecutionPolicy。
- [ ] 根据 Router 结果创建策略。
- [ ] 实现执行中策略升级和预算调整。
- [ ] 支持 steering，并将追加约束写入 UserTask 和 TaskMemory。
- [ ] 定义 Requirement、PlanStep、依赖、状态和计划版本。
- [ ] 生成原始需求到计划步骤的覆盖关系。
- [ ] 对结构相同的步骤去重，语义合并时保留全部需求映射。
- [ ] 缺少外部信息时返回澄清或 blocked，不虚构前置任务。
- [ ] 工具结果、steering 或验证失败后允许重新规划。
- [ ] 记录计划版本和变更原因。

### 验收

- 高频问答不加载写工具和长计划。
- 每条原始要求都有计划步骤覆盖或明确澄清。
- 计划可以因真实工具结果改变。
- 策略升级不会扩大权限。

---

## 12. 结果验证

### 目标

用实际 diff 和检查证据决定代码任务是否完成。

### 默认实现

编辑任务在了解仓库后建立 `VerificationContract`。验证来源按顺序合并：

1. 用户明确要求；
2. `AGENTS.md`；
3. 与修改文件相关的现有测试和检查；
4. Agent 建议的最小必要验证。

最终状态由确定性函数计算。

### 任务

- [ ] 定义 VerificationContract 和 VerificationResult。
- [ ] 从项目规则和仓库配置发现检查命令。
- [ ] 允许用户补充或取消非强制检查。
- [ ] 通过 Python shell 工具运行验证。
- [ ] 汇总 diff、检查结果、未验证事项和风险。
- [ ] 实现 success、partial、unverified、blocked 和 failed 判定。
- [ ] 接入 `/verify` 和最终结果事件。

### 验收

- 强制验证失败或未执行时不能返回 success。
- 无法验证时返回 unverified 和原因。
- 只读回答不会被强制运行测试。
- 最终结论能定位到 diff 和验证记录。

---

## 13. 失败恢复

### 目标

区分模型、环境、代码和 Context 失败，并避免机械重试。

### 默认实现

- 模型失败：退避、有限重试或明确切换模型；
- 环境失败：报告依赖、权限或网络条件；
- 代码失败：分析测试证据并重新规划；
- Context 失败：补充搜索、读取或使旧事实失效。

### 任务

- [x] 已有相同调用、参数和错误的重复保护。
- [ ] 定义统一 RuntimeErrorCategory。
- [ ] 实现模型和工具错误分类器。
- [ ] 为每类错误定义恢复动作和最大次数。
- [ ] 将恢复动作写入计划、状态和 Trace。
- [ ] 处理模型流中断和不完整 tool call。
- [ ] 无安全恢复路径时收敛为 blocked 或 failed。
- [ ] 编写限流、环境缺失、测试失败、Context 遗漏和重复失败测试。

### 验收

- 相同失败不会无限循环。
- 测试失败不会被误判为模型失败。
- 环境缺失不会触发无意义代码修改。
- 每次重试都能说明新增信息或策略变化。

---

## 14. Trace、成本与 Eval

### 目标

解释一次任务的执行过程，并用可重复任务验证策略效果。

### 默认实现

Trace 继续使用本地追加式 JSONL，记录 Runtime 自己的事件，不把 LangChain callback 当作权威 Trace。模型 Adapter 提供模型调用、usage 和延迟信息，Tool Runtime 提供工具生命周期。

### 任务

- [x] 已定义 thinking、tool_call、tool_result 和 checkpoint 事件。
- [x] 已实现 JSONL Writer、基础脱敏和执行 Context 投影。
- [ ] 定义 Trace ID、Span ID 和全部 Runtime 事件映射。
- [ ] 记录路由、模型、Prompt 版本、Context 来源、权限、计划和验证。
- [ ] 汇总首 token 延迟、总耗时、token、缓存和费用。
- [ ] 对工具参数、输出和用户内容继续执行敏感信息过滤。
- [ ] 接入 `/trace`、`/cost` 和 JSON 输出。
- [ ] 定义 Eval 仓库任务格式和固定 fixture。
- [ ] 用 mock model 实现故障注入和确定性回归。
- [ ] 支持 baseline 与 candidate 对比。
- [ ] 输出机器可读结果和简洁 Markdown 报告。

### 验收

- 每个模型调用、工具调用和验证都关联同一 task/trace。
- Trace 不保存密钥、隐藏思维链或完整环境变量。
- Eval 可以定位到失败任务的 Trace。
- 策略比较同时报告质量、延迟和成本。

---

## 15. TUI、CLI 与结构化输出

### 目标

提供类似 Codex CLI 的自然语言终端入口，并让所有入口复用同一 Runtime。

### 默认实现

- `picode`：启动 Textual TUI；
- `picode -p "..."`：单次执行；
- `picode --json -p "..."`：只输出结构化事件；
- `picode eval`：运行评估。

TUI 订阅 Runtime Event，不直接调用模型或工具。

### 任务

- [ ] 使用 Typer 建立 `picode` 命令入口。
- [ ] 建立 Textual 输入、消息流和状态区域。
- [ ] 显示流式文本、工具卡片、计划、diff 和验证。
- [ ] 实现权限确认、拒绝和可选参数编辑。
- [ ] 实现 steering 和取消。
- [ ] 实现 `/plan`、`/diff`、`/verify`、`/context`、`/trace`、`/cost`。
- [ ] Phase 2 实现 `/tasks` 和 `/resume`。
- [ ] print、JSON 和 TUI 复用同一 Runtime Controller。
- [ ] 为无 TTY、JSON 纯净输出和关闭取消编写测试。

### 验收

- 用户启动后直接输入自然语言，不选择内部模式。
- 写入前能看到工具、目标和权限范围。
- JSON 模式不混入普通文本。
- TUI 退出时 Runtime 安全取消或保存快照。

---

## 16. 实施顺序与阶段交付

### 当前下一步：架构迁移最小链路

1. 固定 `langchain-core` 和 `langchain-openai`。
2. 定义 ModelGateway 与 RuntimeEvent。
3. 实现最小 Agent Loop。
4. 实现一个只读 read 工具。
5. 用 mock model 跑通确定性循环。
6. 用 DeepSeek 受控跑通一次真实 tool call。

只有这条链路通过后，才迁移权限、完整工具和 TUI。

### Phase 1：可使用的单进程 Coding Agent

- [ ] 自研 Agent Loop 与 DeepSeek 工具调用可用。
- [ ] Router 和两类执行策略接入 Runtime。
- [ ] read、search、edit、shell 与权限可用。
- [ ] 初始/执行 Context 和内存 TaskMemory 可用。
- [ ] 修改任务能展示 diff、运行验证并计算最终状态。
- [ ] 当前会话 Trace、成本、CLI 和基础 TUI 可用。

### Phase 2：长任务可靠性

- [ ] SQLite RuntimeSnapshot 和 TaskMemory 可恢复。
- [ ] 权限等待、暂停和进程退出后恢复可用。
- [ ] 仓库变化检测和安全恢复可用。
- [ ] Context 压缩和完整 Trace 查询可用。

### Phase 3：效果优化

- [ ] 仓库任务集和故障注入可重复运行。
- [ ] baseline 与 candidate 报告可生成。
- [ ] 第二个模型 Provider 接入并验证路由/降级。
- [ ] 至少一项 Context、模型或恢复优化有数据证明收益。

---

## 17. 统一开发与验证要求

每个功能按以下顺序交付：

1. 定义 Python 类型和职责边界。
2. 使用 mock model/tool 编写确定性测试。
3. 实现核心逻辑并通过 pytest、Ruff 和 Pyright。
4. 再接入受控真实模型测试。
5. 最后接入 TUI。

约束：

- 模型测试默认不调用付费 API。
- 不把 LangChain 类型扩散到 Runtime State、TaskMemory 和 SQLite。
- 不让 TUI 保存第二份权威状态。
- 不为了演示加入固定 Bug 修复 workflow。
- 不默认引入多 Agent、向量数据库、独立 Gateway 或云服务。
- 不自动提交、推送、合并或部署。
- 旧 TypeScript 文件的移除需要单独确认。
