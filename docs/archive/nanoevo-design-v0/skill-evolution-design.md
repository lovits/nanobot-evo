# nanobot Skill 自进化扩展设计

> **归档快照**：本文件是方案收敛前的总览稿，不再作为实现依据。当前版本见 `../../nanoevo-design.md`。

> 项目暂定名：**nanobot-evo**
> 定位：在不改变 nanobot 原有 Agent 执行逻辑的前提下，为其增加一个受控、可追溯、可回滚的 Workspace Skill 自进化闭环。
> 状态：实现前设计基线。

## 文档导航

- 原版 nanobot 架构与各模块：[`nanobot-current-architecture.md`](./nanobot-current-architecture.md)
- Hermes 源码依据、借鉴边界和串联方案：[`hermes-inspired-skill-evolution.md`](./hermes-inspired-skill-evolution.md)
- Skill 自进化字段、接口和文件级设计：[`skill-evolution-module-design.md`](./skill-evolution-module-design.md)
- 一周详细执行计划：[`skill-evolution-implementation-plan.md`](./skill-evolution-implementation-plan.md)

本文保留为产品定位、原版对比、验收和面试叙事的总览文档。

“借鉴 Hermes”的准确含义不是复制其全部 Curator，而是复用其四个关键思想：

- 正常任务与任务后复盘分离；
- Fork 隔离 Agent 做 Skill Review；
- 默认复用主模型，同时允许切换后台模型；
- Review Agent 只能使用受限的 Skill 管理工具。

本项目进一步把它收敛为“按 Skill 归因、只修订已有 Workspace Skill、永远禁止修改内置 Skill、必须人工批准”。具体源码映射和差异见上述 Hermes 对齐文档。

## 1. 项目为什么值得做

原版 nanobot 已经解决了“如何让大模型通过 Agent Loop 调用工具完成任务”：

- 接收用户任务；
- 构建上下文并加载 Skill；
- 调用模型；
- 执行文件、Shell、Web、MCP 等工具；
- 保存会话和记忆；
- 返回结果。

但普通 Agent 的一次执行通常是一次性过程。即使它在真实任务中发现某个 Skill 的步骤过时、描述错误或流程不完整，这些经验也不会自动进入该 Skill。下一次相似任务仍可能重复踩坑。

本项目研究并实现的问题是：

> Agent 如何依据真实任务轨迹，发现已有 Skill 的缺陷，并把可泛化的经验沉淀为经过验证和人工批准的 Skill 修订？

它不是另一个聊天机器人，也不是一个新的业务 Agent。它是 nanobot 的一个能力增强层：

```text
原版 nanobot：任务 → 执行 → 返回结果

nanobot-evo：任务 → 执行 → 留下证据 → 复盘已有 Skill
             → 生成修订提案 → 人工批准 → 后续任务使用新版 Skill
```

这个选题同时体现：

- Agent Runtime 扩展能力；
- Hook 与低耦合架构设计；
- 执行轨迹与可观测性；
- 反思和经验泛化；
- Skill 生命周期与安全治理；
- 用真实仓库验证 Agent 改进的实验意识。

## 2. 项目边界

### 2.1 V1 要做什么

V1 只实现一条完整且可演示的闭环：

1. 观察正常 Agent 任务；
2. 判断任务实际使用了哪个 Workspace Skill；
3. 保存最近任务的结构化轨迹；
4. 满足触发条件后启动后台 Review 子 Agent；
5. 子 Agent 基于轨迹判断是否需要改进；
6. 如有充分证据，产生一个局部 Patch 提案；
7. 用户在聊天中批准或拒绝；
8. 批准后备份旧版本并修改 Workspace Skill；
9. 下一次正常任务自然加载新版 Skill。

### 2.2 V1 明确不做什么

- 不创建全新的 Skill；
- 不修改 nanobot 内置 Skill；
- 不让 Agent 自动批准自己的修改；
- 不自动修改 Python 源码；
- 不训练或微调模型；
- 不使用 RL；
- 不做多 Agent 协作平台；
- 不做通用 Agent 评测平台；
- 不新增 WebUI 管理页面；
- 不使用隐藏思维链作为证据；
- 不把某个仓库的具体答案硬编码进 Skill；
- 不保证每次 Review 都产生修改。

“自进化”在本项目中的准确含义是：

> 依据历史执行证据，持续修订已有 Workspace Skill 的显式操作知识。

它不是模型权重学习，也不是无边界的自我改写。

## 3. 原项目与优化后项目对比

| 维度 | 原版 nanobot | nanobot-evo |
|---|---|---|
| 核心目标 | 轻量级通用 Agent Runtime | 在原 Runtime 外增加 Skill 自进化闭环 |
| Agent Loop | 模型推理、工具调用、观察、继续执行 | 完全复用，不重写 |
| Skill 来源 | 内置 Skill、用户安装或人工维护的 Workspace Skill | 仍使用原来源，但允许受控修订已有 Workspace Skill |
| Skill 使用 | `always: true` 自动注入；其他 Skill 按需读取 | 保持原逻辑，同时记录某个 Skill 是否被真实使用 |
| 任务结束 | 保存会话并返回结果 | 返回结果不受阻塞；后台追加轨迹并判断是否 Review |
| 经验沉淀 | 会话历史和长期 Memory | 增加面向 Skill 改进的结构化轨迹 |
| 失败处理 | 当前任务内重试或返回错误 | 失败可触发一次面向 Skill 的后台复盘 |
| Skill 质量改进 | 主要依赖人工编辑 | Review 子 Agent 自动生成局部修订提案 |
| 修改权限 | 普通工具按既有权限运行 | 只允许 Patch 已有 Workspace Skill，且必须人工批准 |
| 修改安全 | 原有 Workspace 边界 | 增加目标限制、哈希校验、格式校验、备份和恢复 |
| 可追溯性 | 会话与工具执行日志 | 轨迹、证据 ID、提案、审批和版本历史永久保存 |
| 用户界面 | CLI、WebUI 和聊天渠道 | 沿用现有聊天界面，新增 `/evolve` 命令 |
| 评估方式 | 无专门的 Skill 进化实验 | 使用真实 Python 仓库做离线前后对比 |

最重要的区别不是“多了一个 Skills 文件夹”，而是多了一条治理完整的状态链：

```text
Observed → Review Due → No Change / Proposed
         → Approved / Rejected / Conflict
         → Applied → Restored
```

## 4. `repo-analysis` 是什么

`repo-analysis` 是 V1 的代表性 Workspace Skill，不是新框架，也不是另一个 Agent。

它是一份教 Agent 如何分析 Python 仓库的 `SKILL.md`，例如：

```text
workspace/
└── skills/
    └── repo-analysis/
        └── SKILL.md
```

它初始由项目提供一个合理但不完美的版本，包含：

- 先读项目元数据；
- 定位包和入口点；
- 识别测试目录与配置；
- 搜索核心模块；
- 用真实文件路径支撑结论；
- 输出项目用途、架构、运行流程和风险。

选择它作为代表性 Skill 的原因：

- 用户结果容易理解和展示；
- Python 仓库的事实可以自动检查；
- 真实仓库之间存在可迁移经验；
- 容易观察无效搜索、错误路径和无依据结论；
- 一周内能完成实现与实验。

`repo-analysis` 只是用来证明通用机制的样例。自进化框架本身不应包含任何只针对该 Skill 的业务分支。

## 5. 总体架构

nanobot-evo 采用 Sidecar/Control Plane 结构。原有 Agent 执行路径是 Data Plane，进化功能只在边缘观察和治理。

```mermaid
flowchart TB
    User["用户任务"] --> Loop["原 AgentLoop"]
    Loop --> Build["原 ContextBuilder / SkillsLoader"]
    Build --> Runner["原 AgentRunner"]
    Runner <--> Tools["原 Tool Registry"]
    Runner --> Reply["原回复流程"]

    Runner -. 生命周期事件 .-> Hook["SkillEvolutionHook"]
    Hook --> Trace["Trajectory Store"]
    Trace --> Trigger["Review Trigger"]
    Trigger --> Reviewer["受限 Review 子 Agent"]
    Reviewer --> Decision{"是否有充分证据？"}
    Decision -->|否| NoChange["no_change，静默结束"]
    Decision -->|是| Proposal["Patch Proposal"]
    Proposal --> Gate["Deterministic Gate"]
    Gate --> Approval["聊天内人工审批"]
    Approval -->|批准| Apply["备份并 Patch Workspace Skill"]
    Approval -->|拒绝| Reject["保留记录，不修改"]
    Apply --> Build
```

### 5.1 为什么插在 Hook

Hook 已经能够观察：

- Run 开始和结束；
- 每次工具调用；
- 工具参数；
- 工具结果；
- 工具错误；
- Stop reason；
- Token usage。

因此无需修改 `AgentRunner` 的推理和工具循环。

最佳插入方式是：

> 在 Hook 中观察，在后台子 Agent 中复盘，在 Command 中审批，在下一次 BUILD 时自然加载新版 Skill。

### 5.2 四个具体接入点

#### A. 组装期：`AgentLoop.from_config`

当 `evolution.enabled=true` 时安装扩展：

- 创建 `EvolutionService`；
- 注册 Hook Factory；
- 注册 `skill_manage` 工具；
- 注册 `/evolve` 命令。

关闭时不注册任何扩展，原版行为保持不变。

#### B. 执行期：`AgentHook`

使用这些生命周期方法：

- `before_execute_tool`：记录工具名和已脱敏参数，并识别 Skill 读取；
- `after_execute_tool`：记录截断后的结果和成功状态；
- `on_execute_tool_error`：记录客观工具错误；
- `after_run`：形成轨迹，只调度后台 Review，不阻塞用户回复。

#### C. 管理期：`CommandRouter`

新增：

```text
/evolve
/evolve review <skill> [feedback]
/evolve approve <proposal-id>
/evolve reject <proposal-id>
/evolve restore <skill>
```

#### D. 下一次任务：原 `BUILD`

提案批准后直接修改 Workspace 中已有 `SKILL.md`。下一次构建上下文时，原 `SkillsLoader` 会自然读取新版本，无需修改 Skill 加载逻辑。

## 6. 模块设计

建议新增一个独立包：

```text
nanobot/evolution/
├── __init__.py
├── bootstrap.py     # 向 AgentLoop 安装扩展
├── models.py        # Trace、Review、Proposal 等数据模型
├── hook.py          # 观察正常任务
├── service.py       # 进化用例编排与并发控制
├── store.py         # JSONL、提案和版本历史持久化
├── reviewer.py      # 构建并运行受限 Review 子 Agent
├── patching.py      # Patch 校验、应用、备份和恢复
├── tool.py          # patch-only 的 skill_manage 工具
└── commands.py      # /evolve 命令处理
```

### 6.1 依赖方向

```text
loop.py
  └── evolution.bootstrap
        ├── evolution.service
        ├── evolution.hook
        ├── evolution.tool
        └── evolution.commands

service
  ├── reviewer
  ├── store
  └── patching

reviewer
  └── 原 AgentRunner + 独立受限 ToolRegistry
```

约束：

- `AgentRunner` 不依赖 `evolution`；
- `SkillsLoader` 不依赖 `evolution`；
- `ContextBuilder` 不依赖 `evolution`；
- WebUI、Channel 和 Provider 不依赖 `evolution`；
- 关闭功能后不应产生轨迹、工具或命令。

### 6.2 预计修改的原文件

| 原文件 | 最小改动 |
|---|---|
| `nanobot/config/schema.py` | 增加 `EvolutionConfig` |
| `nanobot/agent/loop.py` | `from_config` 构造完成后调用扩展安装函数 |

如果实现阶段发现可以通过更既有的注册机制完成，应优先进一步减少对 `loop.py` 的改动。

以下核心模块原则上不修改：

- `nanobot/agent/runner.py`
- `nanobot/agent/hook.py`
- `nanobot/agent/skills.py`
- `nanobot/agent/context.py`
- Provider、Channel、Bus 和 WebUI。

## 7. Skill 使用归因

系统只有在确认 Skill 被真实使用后，才允许用本次轨迹改进它。

### 7.1 使用判定

Workspace Skill 满足以下任一条件即视为被使用：

1. Skill 标记为 `always: true`，完整内容已注入本次上下文；
2. Agent 在本次任务中通过 `read_file` 读取了该 Skill 的 `SKILL.md`。

以下情况不算使用：

- Agent 只在 Skill 摘要中看到了名字；
- Skill 被禁用；
- Agent 读取的是内置 Skill；
- 路径无法确定属于配置的 Agent Workspace；
- Review 子 Agent 自己读取 Skill。

### 7.2 单 Skill 与多 Skill

- 本次只使用一个 Workspace Skill：允许自动归因和自动 Review；
- 本次使用多个 Workspace Skill：保存轨迹，但不自动判断责任归属；
- 多 Skill 情况可通过 `/evolve review <skill> [feedback]` 明确指定目标。

这样避免把失败错误归因给不相关的 Skill。

## 8. 轨迹设计

### 8.1 记录什么

每次正常任务保存一个结构化事件：

```json
{
  "trace_id": "tr_01...",
  "created_at": "2026-07-23T12:00:00Z",
  "session_key": "webui:...",
  "task": "分析这个 Python 仓库的结构和入口点",
  "used_skills": ["repo-analysis"],
  "tool_calls": [
    {
      "name": "read_file",
      "params": {"path": "pyproject.toml"},
      "status": "success",
      "result_excerpt": "..."
    }
  ],
  "final_response_excerpt": "...",
  "stop_reason": "completed",
  "error": null,
  "iterations": 6,
  "usage": {"prompt_tokens": 4000, "completion_tokens": 1200}
}
```

### 8.2 不记录什么

- 模型隐藏思维链；
- API Key、Token 和认证头；
- 未经限制的完整文件内容；
- 超长工具输出；
- 与 Skill 复盘无关的二进制或媒体；
- Review 子 Agent 的轨迹。

### 8.3 截断和脱敏

- 字符串结果只保留固定长度摘要；
- 常见 Secret 字段按键名屏蔽；
- Authorization、Cookie、API Key 模式替换为 `[REDACTED]`；
- 文件路径允许保留 Workspace 内相对路径；
- 所有持久化前先执行递归脱敏。

### 8.4 存储

使用标准库和 JSON/JSONL，不增加数据库依赖：

```text
<agent-workspace>/.nanobot/evolution/
├── trajectories.jsonl
├── proposals/
│   └── <proposal-id>.json
├── skill-history/
│   └── <skill-name>/
│       └── <timestamp>-<hash>.md
└── state.json
```

V1 永久保存轨迹，不做轮转和清理。这样实现最简单，也方便演示审计链。若未来轨迹明显增大，再评估归档策略。

注意：存储根目录属于配置的 **Agent Workspace**，不是 WebUI 当前选择的项目 Workspace。

## 9. 触发机制

### 9.1 周期触发

针对每个 Skill 分别计数：

- 第 10、20、30……条新轨迹时触发；
- 每次最多读取该 Skill 最近 10 条轨迹；
- 已审查过的计数记录在 `state.json`。

### 9.2 立即触发

如果本次任务只使用了一个 Workspace Skill，并出现客观失败，则立即 Review，不必等满 10 条：

- Run 抛出错误；
- 异常 Stop；
- 工具执行错误；
- 达到最大迭代次数；
- 任务被中断。

立即 Review 使用当前可用的最近 1–10 条轨迹。

### 9.3 用户反馈触发

用户可执行：

```text
/evolve review repo-analysis 入口点判断错了，应先检查 pyproject.toml
```

用户反馈是额外证据，不代表必须修改。

### 9.4 并发规则

每个 Skill 同时最多一个 Review：

- Review 运行中又达到触发条件时，不再启动第二个；
- 将该 Skill 标记为 `review_pending`；
- 当前 Review 完成后，根据最新轨迹决定是否补跑一次；
- 不同 Skill 可以独立调度。

## 10. Review 子 Agent

### 10.1 为什么使用完整子 Agent

复盘不是一次简单分类。它需要：

- 读取目标 Skill；
- 对照多条真实轨迹；
- 查找反复出现的缺陷；
- 判断经验是否可泛化；
- 必要时形成一个精确 Patch；
- 也可以得出“不应修改”。

因此复用原 `AgentRunner` 构造一个隔离的 Review 子 Agent，比单次 LLM Judge 更贴近 Hermes Agent 的后台 Skill 复盘思路。

### 10.2 模型

- 默认复用当前主模型；
- 可通过 `reviewModelPreset` 选择已有模型预设；
- 预设无效时记录警告并回退主模型；
- Review 模型超时或失败时只记录状态，不重试、不影响主任务。

### 10.3 运行限制

- 最多 8 次迭代；
- 最长 60 秒；
- 最多生成 1 个提案；
- 禁止递归触发进化；
- 不把 Review 过程写入普通任务轨迹。

### 10.4 工具白名单

Review 子 Agent 只允许：

- 读取目标 Workspace Skill；
- 读取选定的最近轨迹；
- 调用 `skill_manage(action="patch")` 提交提案。

它不能：

- 调用 Shell；
- 访问网络；
- 读取任意 Workspace 文件；
- 使用通用写文件工具；
- 创建或删除 Skill；
- 修改内置 Skill；
- 直接应用修改。

### 10.5 Review 的决策标准

只有同时满足以下条件，才能提出 Patch：

1. 缺陷能由轨迹 ID 指向的事实支撑；
2. 缺陷与目标 Skill 内容直接相关；
3. 修订对同类任务具有泛化价值；
4. 修订不是某个仓库的具体答案；
5. 当前没有语义相同的 Pending 提案；
6. 局部 Patch 足以解决，不需要整份重写。

允许产生提案的典型证据：

- Skill 指导导致工具失败；
- 用户明确纠正了 Skill 的做法；
- Skill 内容与仓库真实证据矛盾或已经过时；
- 多条轨迹反复显示同一个流程缺口。

不允许仅凭以下理由修改：

- “写得还能更漂亮”；
- “也许增加更多步骤更全面”；
- 模型主观偏好另一种措辞；
- 单次偶然失败且无法归因；
- 任务本身超出 Skill 范围。

无充分证据时返回：

```json
{"decision": "no_change", "reason": "..."}
```

`no_change` 静默保存，不打扰用户。

## 11. Patch 提案与确定性门禁

### 11.1 提案格式

```json
{
  "proposal_id": "pr_01...",
  "skill": "repo-analysis",
  "base_hash": "sha256:...",
  "evidence_trace_ids": ["tr_01...", "tr_02..."],
  "old_text": "原文中的一段精确文本",
  "new_text": "修订后的文本",
  "reason": "轨迹显示该步骤在多个仓库中会漏掉声明式入口点",
  "status": "pending"
}
```

V1 使用精确 `old_text/new_text` Patch，不做整文件重写。

### 11.2 确定性校验

模型提案进入 Pending 前，代码必须验证：

- 目标 Skill 已存在；
- 目标位于配置的 Agent Workspace 的 `skills/` 下；
- 目标不是 nanobot 内置 Skill；
- `old_text` 在当前文件中恰好出现一次；
- `old_text != new_text`；
- 修改后 YAML Frontmatter 可解析；
- Skill `name` 不变；
- 文件仍满足 Skill 基本结构；
- 修改长度在限制内；
- 不包含绝对路径和 Secret；
- 至少包含一个有效证据轨迹 ID；
- 当前 Skill 没有重复 Pending 提案。

任何一项失败，提案标记为 `invalid`，不通知批准。

### 11.3 为什么必须人工批准

Review 是自动的，Patch 生成也是自动的，但能力定义的最终写入必须由用户批准。

这样实现的是“自动发现与建议、人工控制能力边界”，避免：

- 错误经验污染 Skill；
- Prompt Injection 通过任务轨迹进入长期能力；
- 一次偶发失败造成永久修改；
- Agent 同时担任提案者和批准者。

人工只负责批准或拒绝，不需要手动整理轨迹、编辑 Markdown 或执行实验步骤。

### 11.4 哈希冲突

提案生成时记录 Skill 的 `base_hash`。

批准时：

- 当前哈希等于 `base_hash`：允许应用；
- 当前哈希不同：标记 `conflict`，不尝试自动合并。

这防止用户在 Pending 期间手动修改 Skill 后，被旧提案覆盖。

### 11.5 备份与恢复

批准前把当前 `SKILL.md` 保存到 `skill-history/`。

```text
/evolve restore repo-analysis
```

恢复最近一个历史版本。恢复也产生审计记录，但不会删除旧轨迹和提案。

## 12. 前台 `skill_manage` 工具

正常主 Agent 也可以获得同一个受限工具，但必须满足更严格的运行态条件：

- 本次任务实际使用了目标 Skill；
- 出现客观失败、用户纠正或真实仓库证据冲突；
- 只能 `action="patch"`；
- 只能生成 Pending 提案；
- 不能直接应用；
- 不能创建、删除或修改内置 Skill。

工具通过 Runtime Context 向主 Agent提供简短规则，不修改全局 Prompt 模板。

前台提案是补充路径；主要演示路径仍是任务结束后的后台 Review。

## 13. 配置

只增加两个用户配置项：

```json
{
  "evolution": {
    "enabled": false,
    "reviewModelPreset": null
  }
}
```

含义：

| 字段 | 默认值 | 含义 |
|---|---:|---|
| `enabled` | `false` | 是否安装 Skill 进化扩展 |
| `reviewModelPreset` | `null` | Review 子 Agent 使用的现有模型预设；为空时复用主模型 |

以下参数作为 V1 命名常量，不暴露配置，避免扩大开发量：

- 每 10 条轨迹 Review；
- Review 最近 10 条；
- 最多 8 次迭代；
- 60 秒超时；
- 每次最多 1 个提案；
- 必须人工审批。

## 14. 聊天命令与用户体验

### 14.1 查看状态

```text
/evolve
```

返回：

- 功能是否启用；
- 各 Skill 轨迹数量；
- Review 状态；
- Pending 提案；
- 紧凑 Diff；
- 可执行的批准/拒绝命令。

### 14.2 主动复盘

```text
/evolve review repo-analysis
/evolve review repo-analysis 用户反馈内容
```

该命令触发自动 Review，不要求用户人工分析。

### 14.3 审批

```text
/evolve approve pr_01...
/evolve reject pr_01...
```

### 14.4 恢复

```text
/evolve restore repo-analysis
```

### 14.5 通知

生成有效提案后，通过原 `MessageBus` 向触发该 Review 的聊天发送：

```text
Skill improvement proposed: repo-analysis
Proposal: pr_01...
Reason: ...

- old line
+ new line

/evolve approve pr_01...
/evolve reject pr_01...
```

Review 返回 `no_change` 时不发送消息。

WebUI 已能发送普通聊天命令，因此 V1 不新增前端页面。

## 15. 失败隔离

进化功能不能降低原 nanobot 的可用性。

| 故障 | 行为 |
|---|---|
| 轨迹写入失败 | 记录日志，主任务照常返回 |
| Review 模型失败 | 标记失败，不重试，主任务不受影响 |
| Review 超时 | 取消 Review，保留轨迹 |
| 无效模型预设 | 回退本次主模型并记录警告 |
| Patch 校验失败 | 标记 `invalid`，不修改 Skill |
| Skill 哈希冲突 | 标记 `conflict`，不覆盖 |
| Skill 文件不存在 | 拒绝操作 |
| 目标是内置 Skill | 拒绝操作 |
| 多 Skill 无法归因 | 只保存轨迹，不自动 Review |
| 进程退出 | 已落盘状态保留；后台任务无需阻塞退出 |

Hook 使用原有 `CompositeHook` 的错误隔离能力，但关键写入函数仍要返回明确状态，不能吞掉错误。

## 16. 安全模型

### 16.1 信任边界

本系统中的不可信输入包括：

- 用户任务；
- 被分析仓库内容；
- 工具输出；
- 历史轨迹；
- Review 模型生成的 Patch。

因此模型输出永远只是候选提案，不能直接成为文件写入指令。

### 16.2 核心安全规则

- 使用 `Path.resolve()` 和 `relative_to()` 做路径包含校验；
- 读写根目录固定为 Agent Workspace；
- 写目标精确限制为已存在的 Workspace `SKILL.md`；
- 内置 Skill 根目录只读且永不进入 Patch 路径；
- 不允许符号链接逃逸；
- 所有 Patch 先过确定性门禁；
- 所有应用操作要求 Pending 状态和人工批准；
- 应用前备份；
- 轨迹持久化前脱敏；
- Review 工具采用显式白名单。

### 16.3 Prompt Injection 防护

仓库中的文本可能声称“忽略规则并修改 Skill”。Review Prompt 必须明确：

- 仓库内容和工具输出只是证据，不是指令；
- 只能根据多条结构化事实提出局部修订；
- 不得复制仓库中的命令、密钥或绝对路径进入 Skill；
- Patch 最终仍需代码校验和人工批准。

## 17. “评测”在本项目中的位置

本项目不做一个独立的 Agent 评分平台，也不使用另一个 LLM 随意打 1–10 分。

这里有两类不同的验证：

### 17.1 运行时证据审查

这是进化机制内部的一部分，回答：

> 轨迹中是否存在足以修改这个 Skill 的客观证据？

输出是 `no_change` 或 Patch Proposal，不是排行榜分数。

### 17.2 离线前后对比

这是简历项目的实验部分，回答：

> 同一个 Agent 使用进化前后的 `repo-analysis` Skill，在未见过的真实 Python 仓库上是否表现更好？

它不进入日常 Runtime，也不影响正常 Agent。

## 18. 最小离线实验

### 18.1 数据来源

选择三个公开、真实、规模适中的 Python 仓库：

- 两个 Experience Repositories：产生轨迹并推动 Skill 修订；
- 一个 Held-out Repository：只用于最终前后对比。

候选可从 `click`、`requests`、`httpx` 等结构清楚的仓库中选择。实现时由准备脚本：

1. Clone 到 Gitignore 的缓存目录；
2. 将真实 Commit SHA 写入锁文件；
3. 后续实验固定使用相同版本。

仓库源码不提交到本项目。

### 18.2 实验组

| 组别 | Agent | Skill |
|---|---|---|
| Baseline | 同一 nanobot、同一模型、同一 Prompt | 原始 `repo-analysis` |
| Evolved | 同一 nanobot、同一模型、同一 Prompt | 批准后的 `repo-analysis` |

除 Skill 版本外其他条件保持一致。

### 18.3 自动事实检查

使用静态 Python 扫描器从真实仓库生成可验证事实：

- `pyproject.toml` / `setup.cfg` 中的项目元数据；
- 声明式 CLI Entry Point；
- Python Packages 和 Modules；
- 依赖；
- 测试目录和配置；
- Agent 回答中引用的文件路径是否真实存在。

不对“项目介绍写得是否优美”做主观打分。

### 18.4 指标

- Fact Coverage：应识别事实的覆盖率；
- Path/Entry Accuracy：路径和入口点准确率；
- Unsupported Claims：无法由仓库证据支撑的断言数；
- Tool Calls：工具调用次数；
- Token Usage：模型 Token 消耗。

实验必须调用真实模型和真实仓库，不用 Fake Agent 结果。只有哈希冲突、路径限制、审批和恢复等纯代码逻辑使用 Test Stub。

## 19. 测试策略

### 19.1 单元测试

- Workspace Skill 与内置 Skill 路径识别；
- `always: true` Skill 使用判定；
- `read_file(SKILL.md)` 使用判定；
- 多 Skill 不自动归因；
- 轨迹截断和 Secret 脱敏；
- 每 10 条触发；
- 客观失败立即触发；
- `old_text` 零次、一次、多次匹配；
- YAML Frontmatter 和 `name` 不变；
- Base Hash 冲突；
- Pending 去重；
- Approve、Reject、Restore 状态转换；
- 禁止创建、删除和修改内置 Skill；
- 功能关闭时零注册、零副作用。

### 19.2 集成测试

- 正常 Agent 使用 Workspace Skill 后产生轨迹；
- `after_run` 不等待 Review 完成；
- Review Runner 只能看到白名单工具；
- Review 生成提案但不直接写 Skill；
- Approve 后下一次 Context Build 读取新内容；
- Review 失败不影响主回复；
- WebUI/CLI 均可通过 `/evolve` 管理。

### 19.3 回归测试

实现前后都应验证：

- 原 Agent Loop 测试；
- Hook 组合测试；
- Command Router 测试；
- Skills Loader 测试；
- Config 加载和序列化测试。

项目约束要求运行：

```bash
ruff check nanobot/ tests/
pytest
```

不运行 `ruff format`。

## 20. 验收标准

满足以下条件才算 V1 完成：

1. `evolution.enabled=false` 时原 nanobot 行为和测试不变；
2. 能识别正常任务是否真实使用单个 Workspace Skill；
3. 能永久保存脱敏后的结构化轨迹；
4. 满 10 条或客观失败时能后台启动 Review；
5. Review 使用可切换的模型预设和受限工具；
6. Review 可以返回 `no_change`；
7. 有证据时只能产生一个局部 Patch 提案；
8. 内置 Skill、全新 Skill 和直接写入均被拒绝；
9. 用户能在原聊天界面查看、批准、拒绝和恢复；
10. 哈希冲突不会覆盖用户修改；
11. 批准后下一次任务能自然读取新版 Skill；
12. 至少完成一次真实 Python 仓库的 Baseline/Evolved 对比；
13. README 展示架构、Demo、真实实验和限制。

## 21. 一周实现范围

按每天约 4 小时设计：

| 天数 | 目标 | 交付 |
|---|---|---|
| Day 1 | 数据模型、存储、配置 | Trace/Proposal/State，JSONL 持久化 |
| Day 2 | Hook 与 Skill 使用归因 | 正常任务可产生正确轨迹 |
| Day 3 | Patch 门禁和 `skill_manage` | 只能生成安全 Pending Proposal |
| Day 4 | Review 子 Agent | 自动触发、受限工具、`no_change` |
| Day 5 | `/evolve` 命令 | 状态、Review、Approve、Reject、Restore |
| Day 6 | 测试与真实仓库实验 | 单测、集成测试、Baseline/Evolved 数据 |
| Day 7 | README、Demo 和简历材料 | 架构图、演示录屏、结果表、项目描述 |

如果时间不足，缩减顺序：

1. 保留 Hook、轨迹、Review、提案、审批主闭环；
2. 保留一个真实 Held-out 仓库实验；
3. 简化通知展示；
4. 不增加更多配置和 UI；
5. 不扩展第二种样例 Skill。

## 22. 最终产品功能

完成后，用户能够：

1. 像原来一样使用 nanobot 完成任务；
2. 给 Agent 安装或维护自己的 Workspace Skill；
3. 让系统自动观察这些 Skill 在真实任务中的表现；
4. 在失败或累计足够经验后自动启动复盘；
5. 收到有轨迹证据的 Skill 改进提案；
6. 一条聊天命令批准或拒绝；
7. 在发现退化时恢复旧版本；
8. 查看 Skill 从哪些任务经验中发生了什么变化。

对外一句话：

> nanobot-evo 是一个基于 nanobot 的受控 Skill 自进化 Agent：它通过 Hook 收集真实任务轨迹，使用受限后台子 Agent 复盘已有 Workspace Skill，并通过可审计、需审批、可回滚的局部 Patch，使 Agent 的显式操作知识随使用经验持续改进。

## 23. 简历与面试表达

### 23.1 中文项目描述

> 基于 nanobot 设计并实现受控 Skill 自进化机制：利用生命周期 Hook 采集真实工具执行轨迹，由受限后台子 Agent 进行证据驱动复盘，自动生成已有 Workspace Skill 的局部修订提案；通过路径隔离、哈希冲突检测、人工审批及版本恢复保证演化安全，并在真实 Python 仓库上对比进化前后的事实覆盖率、路径准确率与工具开销。

### 23.2 英文项目描述

> Extended nanobot with a controlled skill-evolution layer that captures real tool-use trajectories through lifecycle hooks, reviews existing workspace skills with a sandboxed background agent, and produces evidence-grounded patch proposals. Added approval, hash-conflict detection, version restoration, and held-out Python repository experiments to make skill improvement safe and measurable.

### 23.3 面试主线

可以按以下顺序讲：

1. **问题**：普通 Agent 完成任务后不会把经验沉淀回操作知识；
2. **观察**：Hermes Agent 使用后台 Agent 做 Skill 复盘，但需要明确写入边界；
3. **设计**：不改 Agent Loop，用 Hook 在边缘观察；
4. **归因**：只有 Skill 被真实读取且单 Skill 使用时才自动 Review；
5. **进化**：最近轨迹 → 受限子 Agent → `no_change` 或局部 Patch；
6. **安全**：Workspace-only、内置只读、确定性校验、人工批准、哈希冲突和恢复；
7. **证明**：真实 Python 仓库、固定 Commit、Held-out 前后对比；
8. **取舍**：V1 不做新 Skill 生成、模型训练和自动批准，以一周完成可靠闭环。

## 24. 关键设计取舍

| 选择 | 原因 | 放弃的方案 | 重新评估条件 |
|---|---|---|---|
| Hook Sidecar | 低耦合，不改主执行状态机 | 在 `AgentRunner` 内硬编码进化 | Hook 无法提供必要事件 |
| 修改已有 Skill | 范围清晰、风险可控 | 自动创建新 Skill | 有成熟分类、去重和生命周期治理 |
| 人工审批 | 防止错误经验永久污染 | Review 后自动写入 | 有充分线上回归与自动验证能力 |
| 精确文本 Patch | 易审查、易校验、Diff 小 | 整文件重写 | Skill 结构化编辑成为必要需求 |
| JSONL + 文件状态 | 无新依赖、一周可完成 | SQLite/向量库 | 数据量或查询并发显著上升 |
| 最近 10 条轨迹 | 成本和证据密度平衡 | 全历史 Prompt | 轨迹增长后需要抽样/聚类 |
| 完整 Review Runner | 能读取证据并形成 Patch | 单次 LLM Judge | Review 行为可被确定性规则替代 |
| 无新 WebUI 页面 | 复用聊天命令、减少工作量 | 专门管理 Dashboard | 项目从简历 Demo 发展为长期产品 |

## 25. 项目成功的准确标准

这个项目的成功不应被描述为“Agent 真的像人一样成长”。

更准确的标准是：

> 在不修改模型参数和原 Agent Loop 的情况下，系统能够从真实任务轨迹中发现已有操作知识的可复用缺陷，安全地产生并管理 Skill 修订，并用未参与进化的真实仓库证明修订没有只记住训练任务。

这既保持了技术诚实，也足以体现 Agent 算法工程岗位所需要的系统设计、实验和可靠性思维。
