# PiCode Coding Agent 产品与工程规格

## 1. 文档目的

本文定义纯 Python 实现的终端 Coding Agent：PiCode。

PiCode 自主实现 Agent Runtime，LangChain 只作为模型、消息和工具 Schema 的适配层。用户进入代码仓库后运行 `picode`，在 TUI 中直接描述目标；Runtime 负责意图识别、Agent Loop、上下文构建、工具执行、权限确认、任务状态、结果验证、Trace 和 Eval。

一句话定位：

> PiCode 是一个终端优先、模型可替换、执行过程可追踪和长任务可恢复的 Coding Agent。

项目首先解决真实代码仓库中的开发任务，其次用可运行、可测试的工程能力对应 TRAE 的 LLM Agent 岗位要求。

---

## 2. 要解决的问题

开发者处理代码任务时，需要在代码搜索、模型问答、文件修改、命令执行、测试和 diff 检查之间反复切换。任务变长后，还会遇到上下文增长、权限控制、工具失败、用户追加要求和进程中断。

PiCode 提供一个自然语言入口。用户只描述目标，系统选择低延迟高频请求或长任务 Agent 请求的执行策略，并在需要产生副作用时申请权限。

### 2.1 真实应用场景

- 理解或审查代码，并给出可定位的证据。
- 修复 Bug、完成小型需求、补充测试并验证结果。
- 处理跨文件修改或 CI 失败，并支持暂停和恢复。

### 2.2 项目价值

PiCode 不以复制 Codex CLI 或 Claude Code 的全部功能为目标。项目重点实现并验证以下机制：

- 自动区分低延迟高频请求和长任务 Agent 请求。
- 开放的模型接入与路由，不绑定单一供应商。
- 可解释的上下文选择和压缩。
- 明确的工具权限边界。
- 由测试、构建或 diff 证据支持的完成判定。
- 可恢复的任务状态和分类恢复策略。
- 可查询的 Trace 与可重复的仓库级 Eval。

---

## 3. 产品使用方式

### 3.1 主入口

用户在代码仓库中运行：

```bash
picode
```

进入 Python TUI 后直接输入自然语言：

```text
这个项目的鉴权流程是怎么工作的？

修复用户注册接口的邮箱校验，并增加相关测试。

根据这段 CI 日志定位失败原因，修好后运行必要检查。
```

用户不需要选择 `ask`、`edit` 或 `task` 模式。执行策略由 Runtime 内部决定。

### 3.2 交互原则

- 只读请求直接执行。
- 实际发生文件写入或高风险命令前再申请权限，不在路由阶段预授予权限。
- 工作区写权限仅对当前仓库、当前任务有效；恢复任务时回到只读。
- 删除、大范围覆盖、提交、推送、部署和外部副作用逐次确认。
- 信息不足时只提出一个必要的澄清问题。
- 用户可以追加约束、改变目标、取消任务或要求立即验证。
- 执行策略可以升级，但权限不能自动扩大。

### 3.3 TUI 展示

首版使用 Python TUI，默认采用 Textual。TUI 只消费 Runtime 事件，不保存权威任务状态，主要展示：

- 流式回复、当前状态和模型；
- 当前计划和执行步骤；
- 工具调用、权限确认和错误；
- diff、验证结果和最终结论；
- Context 来源、Trace、耗时和 token；
- 暂停任务和恢复入口。

主要斜杠命令：

```text
/plan      查看当前计划
/diff      查看本次修改
/verify    查看或触发验证
/context   查看当前上下文来源
/trace     查看执行链路
/cost      查看 token、缓存和费用
/tasks     查看任务列表
/resume    恢复任务
/cancel    取消当前任务
```

### 3.4 辅助接口

- `picode -p "..."`：单次非交互请求；
- `picode --json -p "..."`：输出结构化事件；
- Python API：供测试和其他客户端复用 Runtime；
- `picode eval`：运行本地评估集。

---

## 4. 输入与输出

### 4.1 输入

一次任务可以包含：

- 用户原始请求和追加约束；
- 当前仓库、工作目录和未提交改动；
- 从仓库根目录到工作目录生效的 `AGENTS.md`；
- 用户提供的日志、Issue、设计说明或测试结果。

Runtime 不擅自扩大没有明确给出的目标和副作用范围。

### 4.2 输出

最终输出按任务需要包含：

- 答案和对应代码位置；
- 修改文件和可审查 diff；
- 已运行的测试、检查及其结果；
- 未验证事项和剩余风险；
- 任务状态、模型、耗时、token 和 Trace ID。

最终状态统一为：

- `success`：目标完成且所有强制验证通过；
- `partial`：只完成部分目标；
- `unverified`：修改完成，但必要验证无法运行；
- `blocked`：缺少权限、输入或外部条件；
- `failed`：执行失败且当前策略无法恢复；
- `cancelled`：用户取消任务。

模型不能仅凭文字声明成功。强制验证失败或未执行时不能返回 `success`。

---

## 5. 技术选型与现有能力

### 5.1 正式技术栈

| 层 | 默认实现 | 职责 |
| --- | --- | --- |
| TUI / CLI | Textual、Typer | 用户交互和结构化输出 |
| Agent Runtime | PiCode 自研 | Agent Loop、状态机、工具调度、暂停与恢复 |
| 模型适配 | `langchain-core`、`langchain-openai` | 统一消息、流式输出、工具调用和结构化输出 |
| 默认模型 | DeepSeek OpenAI-compatible API | 首个真实模型接入 |
| 数据模型 | Pydantic | Router、任务、工具、Trace 和结果校验 |
| 持久化 | SQLite | 任务快照、暂停和进程恢复 |
| 测试与质量 | pytest、Ruff、Pyright | 单元、契约和故障注入测试 |

不使用 LangGraph、Deep Agents、`create_agent` 或 `AgentExecutor`。LangChain 不决定循环、状态和工具执行，只降低多模型消息格式、流式 tool call 和结构化输出适配成本。

### 5.2 当前已经实现、可迁移的 Python 能力

- Python 3.11+ 项目环境、Pydantic 类型和测试基础；
- Intent Router、结构化路由结果、澄清和 DeepSeek 路由 Provider；
- `AGENTS.md` 与 `UserTask` 初始 Context；
- `TaskMemory` 基础状态；
- `ReActRound`、`ToolCallRecord`、`TaskCheckpoint`；
- 追加式 Trace、脱敏和执行上下文投影；
- 权限状态、失败重复保护和相关测试。

这些能力需要接入新的 Python Agent Loop 和统一 Runtime State，不重新设计一套同名概念。

### 5.3 旧 pi/TypeScript 实现的处理

现有 TypeScript JSONL 协议、Python 子进程管理、PermissionManager 和 Tool Host 是上一版架构的已完成实验。框架迁移期间：

- 暂时保留，不继续扩展；
- 不作为新 Runtime 的依赖；
- 可作为工具安全、事件协议和 TUI 交互的参考；
- 等纯 Python 最小链路通过后，再单独决定保留、归档或移除。

LangChain 通过 `pyproject.toml` 固定版本安装，不复制任何框架源码。

---

## 6. 总体架构

```text
Python TUI / CLI
        │ user input / runtime events
        ▼
PiCode Runtime（自研）
  ├─ Intent Router
  ├─ Execution Policy
  ├─ Context Engine
  ├─ Model Gateway
  ├─ Tool Registry
  ├─ Permission Manager
  ├─ Verification / Recovery
  └─ Trace / Eval
        │
        ├─ Agent Loop：model ⇄ tools
        ├─ Runtime State / Event Bus
        ├─ Permission Wait / Resume
        └─ Checkpoint / Verify / Finalize
                │
                ▼
LangChain Model Adapter + Local Workspace
```

所有核心能力位于同一个 Python 进程。TUI 通过异步事件订阅 Runtime，不通过跨语言 JSONL 控制 Agent。

### 6.1 LangChain 的使用边界

LangChain 仅负责：

- `SystemMessage`、`HumanMessage`、`AIMessage` 和 `ToolMessage` 等统一消息类型；
- `BaseChatModel` 与不同模型 Provider 的基础适配；
- `bind_tools()`、流式消息和 tool call 的统一表示；
- `with_structured_output()` 等结构化输出能力。

PiCode 自己负责：

- Agent Loop、执行状态机和事件顺序；
- 工具注册、权限、执行、超时和结果回填；
- Context、任务记忆、Checkpoint 和进程恢复；
- 失败分类、验证、Trace、成本和 Eval。

LangChain 的对象只出现在 Model Gateway 边界，不进入权限、任务状态和持久化模型。这样可以替换模型适配层，而不改动 Runtime。

### 6.2 自研 Agent Loop

每轮循环按以下顺序运行：

| 阶段 | 职责 |
| --- | --- |
| `prepare` | 从 Runtime State 构建本轮最小 Context 和可用工具 |
| `model` | 通过 LangChain Model Adapter 流式调用模型 |
| `act` | 校验权限，执行零个或多个工具并记录结果 |
| `observe` | 将工具结果写回消息、任务状态和 Trace |
| `decide` | 继续循环、等待用户、进入验证或结束 |

模型决定搜索哪些文件、调用什么工具和如何修改；Runtime 只固定安全、状态、预算和验证边界。权限等待会保存 `PendingAction` 并暂停循环，用户响应后从同一 `taskId` 继续，不依赖框架的 interrupt 机制。

---

## 7. Intent Router 与两类执行策略

Router 输出保持精简：

| 字段 | 含义 |
| --- | --- |
| `intent` | `question`、`inspect`、`review`、`change`、`run` 或 `ambiguous` |
| `executionClass` | `high_frequency`、`long_task_agent` 或 `null` |
| `clarificationQuestion` | 信息不足时的唯一必要问题 |
| `reason` | 可选调试原因 |

示例：

```json
{
  "intent": "change",
  "executionClass": "long_task_agent",
  "clarificationQuestion": null,
  "reason": "请求要求修改代码并补测试。"
}
```

| 执行策略 | 适用请求 | 默认资源策略 |
| --- | --- | --- |
| `high_frequency` | 简单定位、解释和轻量审查 | 小 Context、少量只读工具、不创建长计划 |
| `long_task_agent` | 多轮诊断、修改、测试和跨文件任务 | 动态 Context、任务状态、计划、工具循环和验证合同 |

执行中可以升级策略，但写入权限仍需在实际工具调用时确认。

---

## 8. Context 与任务状态

### 8.1 初始 Context

首次模型请求包含：

1. 从仓库根目录到当前工作目录合并的 `AGENTS.md`；
2. `UserTask`：原始请求、追加约束和明确标注的 Host 执行范围。

工具 Schema 由模型接口单独传递，不重复写入 Prompt。初始 Context 不包含整仓库代码或历史任务。

### 8.2 执行 Context

每轮模型调用只选择当前决策需要的信息：

- 当前目标和未完成事项；
- 最近有效工具结果及证据引用；
- 最近 Checkpoint 和已确认事实；
- 与当前步骤直接相关的代码片段；
- 当前验证状态。

完整工具输出保存在 Trace 或引用文件中，不重复放入 Prompt。

### 8.3 压缩与失效

当上下文接近模型窗口、阶段完成或长输出返回时，生成结构化摘要。摘要必须保留目标、约束、已修改文件、验证证据、未完成事项和失效事实。压缩策略由 Eval 验证后再逐步复杂化。

---

## 9. 模型与 Prompt 策略

Model Gateway 包装 LangChain 模型接口，首版使用 `ChatOpenAI` 的自定义 `base_url` 接入 DeepSeek。后续可以增加 Anthropic 或其他支持 tool calling 的模型。Runtime 只依赖自己的 `ModelRequest`、`ModelEvent` 和 `ModelResult`，避免 LangChain 类型扩散到核心状态。

Model Policy 负责：

- 模型选择与用户手动覆盖；
- 流式文本、可见 thinking、tool call 和 usage 的统一事件；
- Prompt 模板和版本；
- 结构化输出校验；
- Rate Limit、超时、重试和模型降级；
- token、缓存和费用统计。

Prompt 分为项目规则、用户任务、执行状态和动态上下文。API Key 只从环境读取，不进入 Prompt、Checkpoint 或 Trace。

---

## 10. Tool 与权限 Runtime

首版提供四类 Python 原生工具：

- `read`：读取限定范围的文件；
- `search`：文件名和文本搜索；
- `edit`：生成并应用可审查修改；
- `shell`：运行测试、构建、Git 查询和必要命令。

每个工具通过 Pydantic/JSON Schema 描述输入，并声明副作用等级。统一工具包装器负责路径限制、超时、取消、输出上限、参数指纹、结果摘要和 Trace。

权限规则：

- read/search 默认允许；
- edit/write 需要当前任务的工作区写授权；
- Shell 按实际命令分类，无法可靠识别时请求确认；
- 高风险或外部副作用操作逐次确认；
- 拒绝后返回结构化工具结果，模型可以重新规划；
- 权限不能由模型或执行策略直接修改。

---

## 11. 动态计划、验证与恢复

### 11.1 动态计划

只有长任务默认创建计划。计划由模型根据任务和仓库证据生成并更新，不作为 Runtime 预先写死的步骤列表。每个步骤记录目标、完成条件、需求映射、依赖、状态和验证要求。

### 11.2 Verification Contract

编辑任务在了解仓库后建立验证合同。验证项来自：

1. 用户明确要求；
2. `AGENTS.md`；
3. 与修改相关的现有测试和检查；
4. Agent 建议的最小必要检查。

最终状态由确定性函数根据 diff 和验证结果计算。

### 11.3 Recovery

失败先分类：

- 模型失败：限流、超时或无效结构化输出；
- 环境失败：依赖、网络或权限问题；
- 代码失败：测试、构建或行为不符合预期；
- 上下文失败：缺少关键文件或假设错误。

相同工具、相同参数和相同错误不能无限重试。恢复动作必须引入新信息、不同参数或新计划。

---

## 12. Trace、Checkpoint 与 Eval

### 12.1 Trace

Trace 使用追加式事件记录：

- 用户请求、路由和执行策略；
- 模型、Prompt 版本、延迟、token、缓存和费用；
- Context 来源和裁剪原因；
- 可见 thinking 摘要、tool call、tool result；
- 权限变化、计划更新、验证和最终状态。

不保存模型隐藏思维链、密钥或完整环境变量。

### 12.2 Task Checkpoint 与 Runtime Snapshot

- `RuntimeSnapshot`：保存循环位置、消息引用、PendingAction、权限重置标记和恢复所需状态；
- `TaskCheckpoint`：记录已经确认的事实、阶段结果和下一目标，供 Context 与 Trace 使用。

恢复任务时重新检查仓库根目录、Git HEAD、工作区状态和关键文件哈希，权限恢复为只读。

### 12.3 Eval

首批评估覆盖代码定位、小型修改、Bug 修复、diff 审查、中断恢复、模型限流和工具失败。指标包括完成率、强制验证通过率、无效工具调用、恢复成功率、首个有效结果延迟、总耗时、token 和费用。

---

## 13. 实施阶段

### Phase 0：架构迁移验证

- 安装并固定 `langchain-core`、`langchain-openai` 和 Python TUI 依赖；
- 打通 DeepSeek → 自研 Agent Loop → 只读工具 → 流式事件；
- 验证 Agent Loop 的继续、取消、等待权限和内存快照；
- 确认 Windows 原生路径和命令执行可用；
- 迁移验证通过前不删除旧 TS/Python bridge。

### Phase 1：可使用的单进程 Coding Agent

- `picode` 进入 Python TUI；
- Router 和两类执行策略接入统一 Agent Loop；
- 支持代码读取、搜索、编辑和命令执行；
- 支持权限确认、动态计划和 steering；
- 输出 diff、验证结果、最终状态和当前会话 Trace。

### Phase 2：长任务可靠性

- 使用 SQLite 持久化 Runtime Snapshot；
- 支持暂停、取消和进程退出后恢复；
- 实现仓库变化检查、错误分类和有效重试；
- 实现 Context 压缩和完整 Trace 查询。

### Phase 3：效果与成本优化

- 完善模型路由、缓存、限流和降级；
- 建立仓库任务集和故障注入评估；
- 用 Eval 比较 Prompt、模型和 Context 策略。

---

## 14. MVP 验收标准

1. 用户运行 `picode` 后可以仅通过自然语言完成代码问答和修改任务。
2. DeepSeek 在 PiCode 自研 Agent Loop 中完成多轮模型与工具交互。
3. `high_frequency` 不创建不必要的长计划，`long_task_agent` 支持动态计划和 steering。
4. 只读工具无需确认，任何写入和高风险操作都遵守权限边界。
5. Agent 的工具选择由模型和仓库证据决定，不依赖任务类型固定 DAG。
6. 修改任务展示 diff，并用测试、构建或明确的未验证原因支撑最终状态。
7. 当前会话可以查询 Context 来源、Trace、耗时和 token。
8. 单元测试使用 mock model，不默认消耗真实模型额度。

进程退出后恢复和完整 Eval 属于后续阶段。

---

## 15. 与 TRAE 岗位要求的对应

| 岗位要求 | PiCode 对应实现 | 展示证据 |
| --- | --- | --- |
| 代码理解、生成、测试和任务执行 | Python TUI、代码工具、自研 Agent Loop、Verification | 真实仓库问答和 Bug 修复 |
| 模型接入与调度 | LangChain 模型接口、DeepSeek、Model Policy | 模型切换、路由和失败降级 |
| 流式输出、工具调用、结构化输出 | LangChain 模型适配、Runtime Event、工具 Schema、Pydantic | 实时 TUI 和结构化 Trace |
| Prompt 与 Context 管理 | Prompt 版本、ContextEngine、压缩和来源解释 | `/context` 与策略对比 |
| Agent Loop、多轮工具调用和状态 | 自研循环、状态机、steering、Snapshot | 完整执行轨迹和恢复演示 |
| 权限、失败恢复和结果验证 | PendingAction、PermissionManager、Recovery、Verification | 拒绝写入、测试失败后重规划 |
| Tracing 与实验评估 | 本地 Trace、仓库任务集、baseline/candidate | 单任务 Trace 和 Eval 报告 |
| 高频请求与长任务差异化 | `high_frequency` 与 `long_task_agent` | 不同 Context、计划和工具策略 |
| Python 工程能力 | 统一 Python Runtime、异步事件、类型和测试 | 可运行代码、测试和架构说明 |

LangChain 只解决模型接入的重复适配；Agent Loop、Router、Context、工具、权限、状态、恢复、验证、Trace 和 Eval 都由 PiCode 实现。面试时必须明确这个边界。

---

## 16. 非目标与完成定义

首版不做：

- 复刻 Codex 或 Claude Code 的全部能力；
- LangGraph、Deep Agents、预制 Agent Executor 或多 Agent 编排；
- 向量数据库、知识图谱或独立模型 Gateway；
- IDE 插件和低延迟代码补全；
- 自动提交、推送、合并或部署；
- 未经评估证明的复杂 Context 策略。

首个可展示版本必须满足：

- 能在真实仓库中完成至少一条问答链路和一条修改验证链路；
- Agent 决策动态，安全、状态和验证边界确定；
- 修改具有 diff 和验证证据；
- 路由、Context、模型、工具和结果可由 Trace 解释；
- 至少一个失败场景能安全停止或恢复；
- 项目能力可以逐项对应 TRAE 的核心要求。
