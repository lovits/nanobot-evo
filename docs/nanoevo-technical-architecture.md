# nanoevo 技术架构

> 本文定义 nanoevo V1 的代码级架构，包括字段、状态、接口、文件改动、运行流程和与原项目的对齐方式。
> 上游现状见 [`nanobot-current-architecture.md`](./nanobot-current-architecture.md)。
> 功能与 Hermes 借鉴边界见 [`nanoevo-design.md`](./nanoevo-design.md)；原版对比见 [`nanobot-vs-nanoevo.md`](./nanobot-vs-nanoevo.md)。

## 1. 设计目标

在不改变原 Agent Loop 行为的前提下，让 nanobot 能够：

1. 观察已有 Workspace Skill 在真实任务中的使用过程；
2. 保存脱敏、结构化的执行轨迹；
3. 在失败或积累足够轨迹后自动复盘；
4. 使用受限后台子 Agent 判断 Skill 是否需要修改；
5. 只对已有 Workspace Skill 生成局部 Patch；
6. 在人工批准后应用；
7. 保留版本历史并支持恢复。

核心约束：

- Skill 自进化是主线；
- 不创建新 Skill；
- 不修改内置 Skill；
- Review 自动运行；
- 修改不是强制的，允许 `no_change`；
- 默认复用主模型，可配置切换；
- 每个 Skill Review 最近 10 条轨迹；
- 周期复盘支持每 5/10/20/100 条可归因轨迹触发，默认 10 条；
- 客观失败立即触发，不受周期阈值限制；
- 自动 Proposal 至少需要两个不同任务的独立证据；
- 用户通过手动 Review 明确纠正时允许一条可验证证据；
- 最多 8 次 Review 迭代、60 秒、1 个提案；
- 所有轨迹永久保存；
- 提案必须人工批准。

## 2. 架构定位

```mermaid
flowchart LR
    subgraph Existing["原 nanobot Data Plane"]
        Command["COMMAND"]
        Build["BUILD / SkillsLoader"]
        Run["RUN / AgentRunner"]
        Save["SAVE"]
        Respond["RESPOND"]
        Command --> Build --> Run --> Save --> Respond
    end

    subgraph Evolution["Skill Evolution Control Plane"]
        Hook["SkillEvolutionHook"]
        Store["EvolutionStore"]
        Trigger["ReviewScheduler"]
        Reviewer["Review Agent"]
        Gate["PatchPolicy"]
        Proposal["Proposal Store"]
        Approval["/evolve approval"]
    end

    Run -. tool/run events .-> Hook
    Hook --> Store --> Trigger --> Reviewer --> Gate --> Proposal
    Command -. management .-> Approval
    Approval --> Proposal
    Proposal -. approved SKILL.md .-> Build
```

原路径不等待进化闭环：

```text
正常 Turn：BUILD → RUN → SAVE → RESPOND
后台路径：RUN Hook → Trace → Schedule Review → Proposal
管理路径：COMMAND → Approve/Reject/Restore
```

## 3. 包结构

新增：

```text
nanobot/evolution/
├── __init__.py
├── bootstrap.py
├── constants.py
├── models.py
├── redaction.py
├── store.py
├── attribution.py
├── hook.py
├── policy.py
├── patching.py
├── service.py
├── reviewer.py
├── tool.py
├── commands.py
└── prompts.py
```

职责：

| 文件 | 责任 |
|---|---|
| `bootstrap.py` | 根据配置把 Service、Hook、Tool、Command 装配到 AgentLoop |
| `constants.py` | V1 固定阈值和大小限制 |
| `models.py` | 轨迹、Review、Proposal、状态等 DTO |
| `redaction.py` | 参数和工具结果递归脱敏、截断 |
| `store.py` | JSONL、Proposal、State、History 的持久化 |
| `attribution.py` | Skill 路径解析和“是否实际使用”判断 |
| `hook.py` | 收集一个正常 Turn 的结构化事件 |
| `policy.py` | 是否允许 Review/提案的业务规则 |
| `patching.py` | Patch 校验、哈希、备份、应用、恢复 |
| `service.py` | 核心用例编排、活动 Turn、Review 并发和通知 |
| `reviewer.py` | 构建受限 AgentRunner 并执行 Review |
| `tool.py` | `skill_manage(action="patch")` |
| `commands.py` | `/evolve` 命令 |
| `prompts.py` | Review System Prompt 和输出约束 |

不新增第三方依赖。

## 4. 配置字段

修改 `nanobot/config/schema.py`。

```python
class EvolutionConfig(Base):
    enabled: bool = False
    review_model_preset: str | None = None


class Config(BaseSettings):
    ...
    evolution: EvolutionConfig = Field(default_factory=EvolutionConfig)
```

JSON：

```json
{
  "evolution": {
    "enabled": false,
    "reviewModelPreset": null
  }
}
```

字段：

| Python 字段 | JSON 字段 | 类型 | 默认值 | 含义 |
|---|---|---:|---:|---|
| `enabled` | `enabled` | `bool` | `false` | 是否安装进化扩展 |
| `review_every_n_trajectories` | `reviewEveryNTrajectories` | `Literal[5, 10, 20, 100]` | `10` | 同一 Skill 累计多少条新轨迹后周期复盘 |
| `review_model_preset` | `reviewModelPreset` | `str \| null` | `null` | Review 模型预设；空值复用当前主模型 |

周期复盘的允许值由 `REVIEW_INTERVAL_OPTIONS` 统一约束。其余运行上限不暴露给用户：

```python
REVIEW_INTERVAL_OPTIONS = (5, 10, 20, 100)
REVIEW_TRAJECTORY_WINDOW = 10
REVIEW_MAX_ITERATIONS = 8
REVIEW_TIMEOUT_SECONDS = 60
MAX_PROPOSALS_PER_REVIEW = 1
MAX_TOOL_RESULT_CHARS = 4_000
MAX_FINAL_RESPONSE_CHARS = 4_000
MAX_PATCH_CHARS = 8_000
REVIEW_MAX_TOOL_RESULT_CHARS = 16_000
REVIEW_FINAL_EXCERPT_BUDGET = 8_000
```

## 5. 数据模型

内部 DTO 使用 Python snake_case；持久化 JSON 也使用 snake_case，避免在内部数据上增加别名复杂度。

### 5.1 枚举

```python
class ToolEventStatus(StrEnum):
    SUCCESS = "success"
    ERROR = "error"


class ReviewTrigger(StrEnum):
    PERIODIC = "periodic"
    OBJECTIVE_FAILURE = "objective_failure"
    MANUAL = "manual"


class ReviewDecision(StrEnum):
    NO_CHANGE = "no_change"
    PROPOSE_PATCH = "propose_patch"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


class ProposalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"
    INVALID = "invalid"
    CONFLICT = "conflict"
    RESTORED = "restored"
```

### 5.2 `EvolutionToolEvent`

一条模型工具调用的可观测记录。

```python
@dataclass(frozen=True, slots=True)
class EvolutionToolEvent:
    call_id: str
    name: str
    params: dict[str, Any]
    status: ToolEventStatus
    result_excerpt: str | None
    error: str | None
    iteration: int
```

| 字段 | 来源 | 说明 |
|---|---|---|
| `call_id` | `ToolCallRequest` | 对应一次工具调用 |
| `name` | Tool | 工具名 |
| `params` | Hook 参数 | 已脱敏、限制深度和长度 |
| `status` | Hook 回调 | 成功或失败 |
| `result_excerpt` | 工具结果 | 截断后的字符串 |
| `error` | Tool Error | 脱敏后的错误 |
| `iteration` | `AgentHookContext` | 发生在哪次 Agent 迭代 |

不保存隐藏 Thought/Chain-of-Thought。

### 5.3 `SkillTrajectory`

一次普通 Turn 的进化证据。

```python
@dataclass(frozen=True, slots=True)
class SkillTrajectory:
    schema_version: int
    trace_id: str
    created_at: str
    turn_id: str
    session_key: str | None
    channel: str
    chat_id: str
    task: str
    used_skills: tuple[str, ...]
    tool_events: tuple[EvolutionToolEvent, ...]
    final_response_excerpt: str | None
    stop_reason: str | None
    error: str | None
    iterations: int
    prompt_tokens: int
    completion_tokens: int
    objective_failure: bool
    project_scope_hash: str | None
```

字段规则：

- `schema_version`：V1 固定 `1`；
- `trace_id`：创建 Hook 时生成，建议前缀 `tr_`；
- `turn_id`：复用 `RequestContext.turn_id`；
- `task`：原始用户文本，截断并脱敏；
- `used_skills`：排序、去重，只包含 Workspace Skill；
- `iterations`：最后观察到的 iteration + 1；
- `objective_failure`：由确定性规则计算，不由 LLM 判断。
- `project_scope_hash`：对 `RequestContext.workspace` 的规范化路径做 SHA-256 后截断得到，仅用于轨迹来源审计，不保存绝对路径，也不参与 Proposal 门禁。

客观失败判定：

```text
run error
OR cancelled/interrupted
OR max_iterations
OR any tool event status == error
OR abnormal stop reason
```

### 5.4 `ReviewRequest`

```python
@dataclass(frozen=True, slots=True)
class ReviewRequest:
    review_id: str
    skill_name: str
    trigger: ReviewTrigger
    trajectory_ids: tuple[str, ...]
    user_feedback: str | None
    source_channel: str
    source_chat_id: str
    requested_at: str
```

约束：

- `trajectory_ids` 为目标 Skill 最近 1–10 条；
- 自动 Review 只允许一个 `skill_name`；
- `user_feedback` 只在手动命令存在；
- Channel/Chat ID 仅用于把提案通知发回原会话。

### 5.5 `SkillPatch`

```python
@dataclass(frozen=True, slots=True)
class SkillPatch:
    old_text: str
    new_text: str
```

约束：

- 只支持一个局部替换；
- `old_text` 必须在当前 Skill 中精确出现一次；
- 不支持统一 Diff、多文件 Patch 或完整文件重写。

### 5.6 `SkillProposal`

```python
@dataclass(frozen=True, slots=True)
class SkillProposal:
    schema_version: int
    proposal_id: str
    review_id: str | None
    skill_name: str
    base_hash: str
    evidence_trace_ids: tuple[str, ...]
    reason: str
    patch: SkillPatch
    status: ProposalStatus
    created_at: str
    decided_at: str | None
    applied_at: str | None
    restored_at: str | None
    validation_error: str | None
```

说明：

- `review_id=None` 表示由前台主 Agent 的 `skill_manage` 提出；
- `base_hash` 使用当前 `SKILL.md` 内容的 SHA-256；
- `status=pending` 的提案不参与正常任务；
- 状态更新采用“读取旧对象 → 生成新对象 → 原子替换文件”。

### 5.7 `SkillReviewState`

每个 Skill 的调度状态。

```python
@dataclass(frozen=True, slots=True)
class SkillReviewState:
    skill_name: str
    trajectory_count: int
    last_reviewed_count: int
    review_running: bool
    review_pending: bool
    active_review_id: str | None
    last_reviewed_at: str | None
    last_decision: ReviewDecision | None
```

### 5.8 `EvolutionState`

```python
@dataclass(frozen=True, slots=True)
class EvolutionState:
    schema_version: int
    skills: dict[str, SkillReviewState]
```

`state.json` 只保存可重建的调度游标，不保存轨迹正文。

### 5.9 `SkillVersionRecord`

版本信息通过文件名和伴随 JSON 保存：

```python
@dataclass(frozen=True, slots=True)
class SkillVersionRecord:
    skill_name: str
    content_hash: str
    proposal_id: str
    created_at: str
    content_file: str
```

## 6. 磁盘布局

```text
<agent-workspace>/.nanobot/evolution/
├── trajectories.jsonl
├── state.json
├── proposals/
│   └── pr_<id>.json
├── reviews/
│   └── rv_<id>.json
└── skill-history/
    └── repo-analysis/
        ├── 20260723T120000Z_<hash>.md
        └── 20260723T120000Z_<hash>.json
```

写入策略：

| 文件 | 策略 |
|---|---|
| `trajectories.jsonl` | Append-only；单条 JSON 一次追加、flush、fsync |
| `state.json` | 临时文件 + fsync + `os.replace()` |
| Proposal/Review JSON | 临时文件 + fsync + `os.replace()` |
| Skill Backup | 写完并 fsync 后才能应用 Patch |
| `SKILL.md` | 临时文件 + fsync + `os.replace()` |

V1 不清理历史文件。

## 7. Skill 使用归因

`attribution.py` 只识别 Workspace Skill。

### 7.1 Path Resolver

输入：

- 配置的 Agent Workspace；
- Tool Name；
- 已转换参数；
- Skill 列表。

输出：

```python
@dataclass(frozen=True, slots=True)
class SkillReference:
    name: str
    path: Path
    source: Literal["workspace"]
```

规则：

1. 对路径 `expanduser().resolve()`；
2. 必须位于 `<agent-workspace>/skills/`；
3. 必须形如 `<skill>/SKILL.md`；
4. 文件必须存在；
5. 不能解析到内置 Skill 根目录；
6. 不能通过符号链接逃逸。

### 7.2 使用判定

- Workspace Skill `always: true`：Hook 创建时加入 `used_skills`；
- 普通 Workspace Skill：只有 `read_file` 成功读取其 `SKILL.md` 才加入；
- 只看到 Context 中的 Skill Summary 不算使用；
- 失败的 `read_file` 不算成功使用；
- Review Agent 的读取不进入普通轨迹。

### 7.3 自动归因

| `used_skills` 数量 | 行为 |
|---:|---|
| 0 | 保存普通轨迹但不触发 Skill Review，或直接跳过进化轨迹 |
| 1 | 允许自动 Review |
| >1 | 保存轨迹，不自动归因 |

V1 建议只持久化至少使用一个 Workspace Skill 的轨迹，减少无关数据。

## 8. Hook 设计

### 8.1 `SkillEvolutionHookFactory`

输入 `AgentTurnHookContext`，返回每 Turn 独立的 `SkillEvolutionHook`。

创建条件：

- 功能启用；
- `ephemeral=False`；
- 不是 Review 子 Agent；
- 有有效 Turn ID/RequestContext。

### 8.2 Hook 内部状态

```python
@dataclass(slots=True)
class MutableTrace:
    trace_id: str
    turn_id: str
    task: str
    used_skills: set[str]
    tool_events: list[EvolutionToolEvent]
    max_iteration: int
```

Hook 生命周期：

| 回调 | 行为 |
|---|---|
| `before_run` | 从 `current_request_context()` 捕获 Turn ID、任务、Runtime；登记活动 Trace；加入 Always Workspace Skills |
| `before_execute_tool` | 暂存脱敏参数和 iteration |
| `after_execute_tool` | 完成 Tool Event；成功读取 Skill 时更新 `used_skills` |
| `on_execute_tool_error` | 记录 Error Tool Event |
| `after_iteration` | 更新最大 iteration |
| `after_run` | 生成不可变 Trajectory，持久化并调度 Review |
| `on_error` | 标记 Run Error |
| `on_finally` | 如果 `after_run` 未执行，持久化 Partial/Error Trajectory；清理活动 Trace |

`after_run/on_finally` 不能直接等待模型 Review，只能调用后台调度函数。

## 9. Review 专用 Tool

V1 不把任何 Evolution Tool 注册到普通主 Agent。`review_evidence` 和
`skill_manage` 只存在于隔离 Review Agent 的私有 `ToolRegistry` 中，因此：

- 正常 Agent 的 Tool 列表和 Prompt 不变；
- 正常 Turn 不能主动创建、批准或应用 Proposal；
- Review Agent 不能读取任意文件，只能读取当前 Review 绑定的 Skill 和轨迹；
- Proposal 仍需用户通过 `/evolve approve` 才能应用。

### 9.1 `skill_manage` 模型可见 Schema

```json
{
  "name": "skill_manage",
  "description": "Propose a trace-grounded patch to an existing workspace skill.",
  "parameters": {
    "type": "object",
    "properties": {
      "action": {"type": "string", "enum": ["patch"]},
      "skill": {"type": "string"},
      "old_text": {"type": "string"},
      "new_text": {"type": "string"},
      "reason": {"type": "string"},
      "evidence_trace_ids": {
        "type": "array",
        "items": {"type": "string"}
      }
    },
    "required": [
      "action",
      "skill",
      "old_text",
      "new_text",
      "reason",
      "evidence_trace_ids"
    ]
  }
}
```

工具只接受 `action="patch"`。

### 9.2 `review_evidence`

`review_evidence` 只支持两个只读动作：

```text
read_skill
read_trajectories
```

目标 Skill 和可读轨迹 ID 在构造 Tool 时已经绑定，模型不能通过参数扩大读取范围。
完整脱敏轨迹永久保存在 JSONL；`read_trajectories` 返回紧凑 Review 投影，
省略大段 Tool Result/参数，并动态分配最终回答摘要预算，从而保证最近 10 条
授权轨迹都能出现在 16,000 字符的 Reviewer 专用结果窗口中。这样不会因第一条
轨迹过长而截掉后续独立证据。

### 9.3 `skill_manage`

Review Agent 的 Service Context 固定：

- 唯一目标 Skill；
- 允许的 Evidence Trace ID 集合；
- 当前 Skill Base Hash；
- 每次 Review 最多一次成功调用。

任何越权字段均返回 `ToolResult.error()`。

Review Agent 只能创建 Pending Proposal，不能 Approve、Apply、Create、Delete 或 Rename。

## 10. Review 调度

### 10.1 正常触发

每个 Skill 单独计数：

```text
trajectory_count - last_reviewed_count >= review_every_n_trajectories
```

阈值可选 5/10/20/100，默认 10；Review 输入始终使用最近 10 条包含该 Skill
的轨迹，避免选择 100 次策略时扩大模型上下文和成本。

### 10.2 立即触发

单 Skill 轨迹出现 `objective_failure=True` 时立即触发。

### 10.3 手动触发

```text
/evolve review <skill> [feedback]
```

手动表示“立即复盘”，不是“强制修改”。

只有 `trigger=manual` 且 `user_feedback` 非空时，才进入“用户明确纠正”例外路径。普通自然语言对话不由代码猜测是否属于纠正，用户使用命令显式表达：

```text
/evolve review repo-analysis 入口点判断错了，应先检查 pyproject.toml
```

### 10.4 合并触发

```text
if review_running:
    review_pending = True
else:
    start_review()
```

当前 Review 结束后：

```text
if review_pending and new eligible trajectories exist:
    start one more review with newest window
else:
    clear review_pending
```

## 11. Review Agent

### 11.1 Runtime 选择

```text
reviewModelPreset 有效
  → ModelRuntimeResolver.resolve_preset(name)

未配置
  → 使用触发 Turn 的 RequestContext.runtime

配置无效
  → 记录 warning，回退触发 Turn Runtime
```

解析 Preset 不改变主 Agent 当前选择。

### 11.2 独立工具注册表

Review Agent 不使用 `loop.tools`，创建新的 `ToolRegistry`：

```text
ReviewToolRegistry
├── review_evidence
└── skill_manage
```

`review_evidence` 支持：

```json
{
  "action": "read_skill | read_trajectories"
}
```

它不接受任意路径，只返回 Service 已绑定的目标 Skill 和轨迹。

### 11.3 AgentRunSpec

关键参数：

| 参数 | 值 |
|---|---|
| `initial_messages` | Review Prompt + ReviewRequest |
| `tools` | 独立 ReviewToolRegistry |
| `runtime` | 上述 Review Runtime |
| `max_iterations` | `8` |
| `max_tool_result_chars` | `4_000` |
| `workspace` | Agent Workspace，但工具不提供通用文件访问 |
| `session_key` | 独立 Review ID |
| `concurrent_tools` | `False` |
| `hook` | 无 Evolution Hook |

整个 `runner.run()` 外包裹 `asyncio.timeout(60)`。

### 11.4 Prompt 输出契约

Review Agent 必须：

1. 读取 Skill；
2. 读取轨迹；
3. 区分 Skill 缺陷与任务/模型偶发失败；
4. 检查可泛化性；
5. 自动 Review 时确认同一缺陷至少出现在两个不同 Turn；
6. 如果证据带有 Project Scope，优先要求来自不同 Project Scope；
7. 手动纠正例外时，将用户反馈与至少一条可观察轨迹对应；
8. 选择 `no_change`，或调用一次 `skill_manage`；
9. 不产生仓库特定答案；
10. 不修改 Skill Name、权限或安全边界。

Review Final Content 只用于 Review Log；Proposal 以 Tool 调用结果为准。

## 12. PatchPolicy

`policy.py` 执行不依赖 LLM 的门禁：

```python
class PatchPolicy:
    def validate_target(...)
    def validate_evidence(...)
    def validate_patch(...)
    def validate_document(...)
    def find_duplicate(...)
```

校验项：

1. Skill 名称安全；
2. Workspace Skill 已存在；
3. 真实路径未逃逸；
4. 目标不是内置 Skill；
5. `old_text` 精确出现一次；
6. `new_text` 非空且不同；
7. Patch 长度受限；
8. 结果仍含合法 YAML Frontmatter；
9. Frontmatter `name` 不变；
10. 不包含绝对路径、Secret 或敏感标记；
11. Evidence ID 存在且属于本次 Review；
12. 所有 Evidence 都与目标 Skill 关联；
13. 自动 Review 至少包含两个不同 `turn_id`，同一 Turn 中的重试只算一条；
14. `project_scope_hash` 不参与 Evidence 数量门禁；
15. 手动纠正例外必须同时满足 `trigger=manual`、非空 `user_feedback` 和至少一条可验证 Evidence；
16. 没有相同 `old_text/new_text` 的 Pending Proposal。

V1 不使用 LLM 分数作为 Gate。

证据门禁在 Proposal 创建时和 Approve 时各执行一次，避免 Proposal Pending 期间轨迹或 Skill 状态发生变化。

## 13. 应用、冲突与恢复

### 13.1 Approve

```text
读取 Pending Proposal
  → 定位 Workspace Skill
  → 重新计算 SHA-256
  → 与 base_hash 比较
  → 再次运行 PatchPolicy
  → 写 Backup
  → 原子写入新 SKILL.md
  → Proposal 状态变为 applied
```

### 13.2 Conflict

当前哈希与 `base_hash` 不同：

- 状态改为 `conflict`；
- 不自动 Merge；
- 不覆盖用户修改；
- 用户可重新触发 Review。

### 13.3 Reject

- `pending → rejected`；
- 不修改 Skill；
- Proposal 永久保留。

### 13.4 Restore

```text
/evolve restore <skill>
```

- 找到最近一个未被恢复的备份；
- 备份当前版本；
- 原子写回历史内容；
- 对应版本记录标为 Restored；
- 轨迹和 Proposal 不删除。

## 14. 命令设计

`commands.py` 提供一个 exact 和一个 prefix handler：

```python
router.exact("/evolve", handle_evolve)
router.prefix("/evolve ", handle_evolve)
```

解析：

| 命令 | Service 方法 |
|---|---|
| `/evolve` | `get_status()` |
| `/evolve review <skill> [feedback]` | `request_review()` |
| `/evolve approve <id>` | `approve_proposal()` |
| `/evolve reject <id>` | `reject_proposal()` |
| `/evolve restore <skill>` | `restore_skill()` |

命令处理器只负责：

- 参数解析；
- 调用 Service；
- 构造 `OutboundMessage`。

它不能直接读写文件或运行 Review。

## 15. Service 接口

```python
class SkillEvolutionService:
    def create_hook(self, turn: AgentTurnHookContext) -> AgentHook | None: ...
    async def record_trajectory(self, trajectory: SkillTrajectory) -> None: ...
    async def request_review(...) -> ReviewRequest: ...
    async def wait_until_idle(self, skill_name: str, ...) -> None: ...
    def get_status(self) -> EvolutionStatusView: ...
    def approve_proposal(self, proposal_id: str) -> SkillProposal: ...
    def reject_proposal(self, proposal_id: str) -> SkillProposal: ...
    def restore_skill(self, skill_name: str) -> SkillProposal: ...
```

依赖通过构造函数注入：

- Agent Workspace；
- EvolutionStore；
- PatchPolicy；
- Reviewer；
- Runtime Resolver；
- Background Scheduler；
- MessageBus。

## 16. Bootstrap 与原项目装配

### 16.1 `AgentLoop.from_config`

原来直接返回 `cls(...)`，调整为：

```python
loop = cls(...)
install_skill_evolution(loop, config.evolution)
return loop
```

`enabled=False` 时安装函数立即返回。

### 16.2 建议增加两个通用公开扩展方法

修改 `nanobot/agent/loop.py`：

```python
def register_hook_factory(self, factory: AgentTurnHookFactory) -> None:
    if factory not in self._hook_factories:
        self._hook_factories.append(factory)


def schedule_background(self, coro: Coroutine[Any, Any, Any]) -> None:
    self._schedule_background(coro)
```

原因：

- 避免 `evolution.bootstrap` 直接访问 `_hook_factories`；
- 避免 Service 调用私有 `_schedule_background`；
- 两个方法是通用扩展能力，不包含 Evolution 业务；
- 保留原 `_schedule_background`，避免影响内部调用。

### 16.3 安装流程

```text
Config enabled
  → 建立 EvolutionStore
  → 建立 PatchPolicy
  → 建立 Reviewer
  → 建立 SkillEvolutionService
  → loop.register_hook_factory(service.create_hook)
  → loop.commands 注册 /evolve
```

`SkillReviewer` 在每次 Review 内单独建立只含 `review_evidence` 和
`skill_manage` 的私有 ToolRegistry；普通 `loop.tools` 不增加工具。

## 17. 与原项目逐项对齐

| 新功能 | 复用的原机制 | 不做的侵入性修改 |
|---|---|---|
| 轨迹采集 | `AgentHook` | 不改 `AgentRunner` |
| Turn 身份 | `RequestContext.turn_id` | 不新增全局可变请求变量 |
| Skill 使用识别 | `SkillsLoader` 路径规则 + `read_file` Tool 事件 | 不改 Skill 加载策略 |
| Review 后台运行 | `AgentRunner`、Loop 后台任务跟踪 | 不建立第二套 Agent 框架 |
| Review 模型切换 | `ModelRuntimeResolver.resolve_preset()` | 不修改主 Session 模型 |
| Patch Tool | `Tool`、`ToolRegistry`、`ToolResult` | 不绕过 Tool Schema |
| 临时规则 | `RuntimeContextProvider` | 不改 System Prompt 模板 |
| 审批命令 | `CommandRouter` | 不新增 Channel 特殊协议 |
| 提案通知 | `MessageBus` / `OutboundMessage` | 不改 Telegram/WebUI |
| 新 Skill 生效 | 下一次 `ContextBuilder`/`SkillsLoader` | 不加缓存失效协议 |
| 状态持久化 | Agent Workspace、本地原子文件 | 不引入数据库 |
| 安全写入 | Workspace Path Resolver 思路、精确 Allowlist | 不开放通用写权限 |

## 18. 修改文件清单

### 18.1 修改的现有文件

| 文件 | 修改内容 | 风险 |
|---|---|---|
| `nanobot/config/schema.py` | 增加 `EvolutionConfig` 和根字段 | 低 |
| `nanobot/agent/loop.py` | `from_config` 安装扩展；增加两个通用注册方法 | 中低 |

不修改：

- `nanobot/agent/runner.py`
- `nanobot/agent/skills.py`
- `nanobot/agent/context.py`
- `nanobot/agent/hook.py`
- Provider、Channel、WebUI 前端。

### 18.2 新增源码

```text
nanobot/evolution/*.py
```

### 18.3 新增测试

```text
tests/evolution/
├── test_models.py
├── test_redaction.py
├── test_attribution.py
├── test_evolution_store.py
├── test_policy.py
├── test_patching.py
├── test_hook.py
├── test_evolution_tool.py
├── test_reviewer_contract.py
├── test_evolution_service.py
├── test_evolution_commands.py
└── test_bootstrap.py
```

另有 `tests/config/test_evolution_config.py`。

### 18.4 Demo 与实验

```text
experiments/nanoevo/
├── agnes-config.example.json
├── README.md
├── repositories.json
├── repo-analysis.SKILL.md
├── results/
│   └── agnes-2.0-flash-20260726.json
└── run_experiment.py
```

## 19. 失败处理

| 失败 | 处理 |
|---|---|
| Trace 写入失败 | Log；主任务继续 |
| Review Runtime 无效 | 回退主 Runtime |
| Review Provider Error | Review 标为 Failed；不重试 |
| Review 超时 | 标为 Timed Out |
| Review Tool 越权 | Tool Error；不产生 Proposal |
| Patch 无效 | Proposal 标为 Invalid |
| Pending 重复 | 返回现有 Proposal |
| Base Hash 改变 | Proposal 标为 Conflict |
| Backup 失败 | 中止 Apply |
| Skill 写入失败 | 保留 Backup 和 Pending/Failure 状态 |
| 通知失败 | Proposal 仍保留，可通过 `/evolve` 查看 |

任何 Evolution 异常都不能向上抛到正常 Agent Turn。

## 20. 安全不变量

实现后必须始终成立：

1. 内置 Skill 永远不可写；
2. 不存在 Create/Delete Skill API；
3. Review Agent 没有 Shell、Web、MCP、通用文件 Tool；
4. 自动 Proposal 至少需要两个不同 Turn 的独立证据；
5. 手动纠正例外必须有非空反馈和可观察轨迹；
6. Pending Proposal 不影响正常 Prompt；
7. 没有人工 Approve 就不能 Apply；
8. Hash 冲突时不能覆盖；
9. 每次 Apply 前必须成功 Backup；
10. 轨迹不能包含 Secret 或隐藏思维链；
11. Project Workspace 不能被当成 Skill 写入根；
12. `enabled=False` 时没有运行时副作用。

## 21. V1 验收接口

功能验收路径：

```text
准备 Workspace repo-analysis Skill
  → 开启 evolution
  → Agent 分析两个不同的真实 Python 仓库并读取 Skill
  → Hook 保存两个不同 Turn/Project Scope 的 Trajectory
  → 失败或满 10 次启动 Review
  → 只有独立证据满足门禁才能提出 Proposal
  → Review 返回 no_change 或 Pending Proposal
  → /evolve 查看 Diff
  → /evolve approve <id>
  → 下一任务加载新版 Skill
  → /evolve restore repo-analysis 可恢复
```

架构验收：

- 原 Runner 零修改；
- 原 Skill Loader 零修改；
- 原 WebUI 零修改；
- 扩展默认关闭；
- 新业务集中在 `nanobot/evolution/`。
