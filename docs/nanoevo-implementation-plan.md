# nanoevo 详细执行计划

> 目标工期：7 天，每天约 4 小时，总计约 28 小时。
> 计划依据：[`nanoevo-design.md`](./nanoevo-design.md) 和 [`nanoevo-technical-architecture.md`](./nanoevo-technical-architecture.md)。
> 原版与改进版边界：[`nanobot-vs-nanoevo.md`](./nanobot-vs-nanoevo.md)。

> 实施状态（2026-07-26）：V1 代码、确定性测试和真实 API 实验已完成；
> 实验使用免费模型 `agnes-2.0-flash`、两个固定 Commit 的 Experience 仓库和
> 一个 Held-out 仓库。真实结果保存于
> [`experiments/nanoevo/results/agnes-2.0-flash-20260726.json`](../experiments/nanoevo/results/agnes-2.0-flash-20260726.json)。
> 最终全量回归为 `5273 passed, 17 skipped`，Ruff 通过。

## 1. 交付目标

一周结束时必须能够演示：

1. 原 nanobot 正常运行；
2. 开启配置后自动记录 Workspace Skill 使用轨迹；
3. 客观失败或累计达到所选 5/10/20/100 条轨迹后自动启动受限 Review Agent；
4. Review 能选择 `no_change`，或在两个不同任务提供独立证据后生成一个局部 Patch Proposal；
5. 用户可在原聊天界面查看、批准、拒绝和恢复；
6. 内置 Skill、创建 Skill、越界路径和直接写入均被拒绝；
7. 在真实 Python 仓库上完成原始 Skill 与进化 Skill 的对比；
8. README 有架构图、Demo、结果、限制和简历描述。

## 2. 实施原则

- 先锁定原行为，再新增能力；
- 每天形成一个可测试的垂直切片；
- 不先做 UI；
- 不引入新依赖；
- 不修改 `AgentRunner`；
- 不把实验脚本混入 Runtime；
- 自动 Proposal 至少需要两个不同 `turn_id`；
- Project Scope 仅作为轨迹来源元数据，不限制 Proposal；
- 只有手动 Review 的非空反馈允许单轨迹纠正例外；
- 每个 Patch 小、可回退；
- 每完成一层就运行对应测试；
- API Key 只通过环境变量提供；
- 不实现或使用 Fake/Stub Provider；
- Review Agent 的模型调用测试和最终实验都使用真实 API；
- 不使用 Fake 实验结果。

## 3. 阶段 0：基线与测试护栏

预计：45 分钟，计入 Day 1 的 4 小时预算，不额外增加总工期。

### 任务

1. 保存当前 Git 状态，确认用户已有修改；
2. 运行 Evolution 将触及的最近测试：
   - Config；
   - Hook；
   - Tool Registry；
   - Skill Loader；
   - Command Router；
   - AgentLoop Runner Integration；
3. 记录基线结果；
4. 建立 `tests/evolution/`；
5. 不修改 `.gitignore` 和 `.codegraph/` 的用户现有状态。

### 验证命令

```bash
pytest \
  tests/config/test_model_presets.py \
  tests/agent/test_turn_hooks.py \
  tests/agent/test_hook_composite.py \
  tests/agent/test_skills_loader.py \
  tests/tools/test_tool_registry.py \
  tests/command/test_router_dispatchable.py \
  tests/agent/test_loop_runner_integration.py -q
```

### 完成标准

- 基线通过，或已有失败被记录且确认与本功能无关；
- 后续能判断是否引入回归。

## 4. Day 1：模型、配置与存储

预算：共 4 小时，其中阶段 0 占 45 分钟，本节功能实现约 3 小时 15 分钟。

### 4.1 配置

修改：

- `nanobot/config/schema.py`
- `tests/config/test_evolution_config.py`

测试：

- 默认关闭；
- camelCase/snake_case 均可加载；
- 序列化输出 `reviewModelPreset`；
- 缺省配置不改变旧配置加载。

### 4.2 数据模型

新增：

- `nanobot/evolution/__init__.py`
- `nanobot/evolution/constants.py`
- `nanobot/evolution/models.py`
- `tests/evolution/test_models.py`

实现：

- Enum；
- DTO；
- `to_dict/from_dict`；
- Schema Version；
- ID 生成；
- ISO 时间。
- `project_scope_hash`，只保存项目作用域指纹，不保存绝对路径。

### 4.3 Store

新增：

- `nanobot/evolution/store.py`
- `tests/evolution/test_evolution_store.py`

实现：

- 创建存储目录；
- Append Trajectory；
- 按 Skill 过滤最近 10 条；
- Proposal/Review 读写；
- State 原子更新；
- Skill History 写入和查询。

### Day 1 验收

```bash
pytest tests/config/test_evolution_config.py tests/evolution/test_models.py tests/evolution/test_evolution_store.py -q
ruff check nanobot/evolution nanobot/config/schema.py tests/evolution tests/config/test_evolution_config.py
```

交付：

- 配置可加载；
- 一条 Trajectory 能持久化并读回；
- Proposal 和 State 可原子保存。

## 5. Day 2：脱敏、Skill 归因与 Hook

预算：4 小时。

### 5.1 Redaction

新增：

- `nanobot/evolution/redaction.py`
- `tests/evolution/test_redaction.py`

覆盖：

- `api_key`、`token`、`authorization`、`cookie`；
- 嵌套 Dict/List；
- 最大深度；
- 字符串截断；
- ToolResult 转换；
- 不可序列化对象。

### 5.2 Attribution

新增：

- `nanobot/evolution/attribution.py`
- `tests/evolution/test_attribution.py`

覆盖：

- Workspace Skill；
- 内置 Skill；
- 同名 Workspace 覆盖；
- `always: true`；
- 成功 `read_file`；
- 失败 `read_file`；
- 不同 Project Workspace 生成不同 Scope Hash；
- 同一 Project Workspace 生成稳定 Scope Hash；
- 符号链接逃逸；
- Project Workspace 与 Agent Workspace 不同。

### 5.3 Hook

新增：

- `nanobot/evolution/hook.py`
- `tests/evolution/test_hook.py`

实现：

- 每 Turn MutableTrace；
- Tool Event；
- Run Result；
- Error/Finally；
- 至少一个 Skill 时持久化；
- Review Agent/Ephemeral Turn 跳过。

### Day 2 验收

构造一个真实 `AgentRunner` 测试：

```text
用户任务
  → read_file(workspace Skill)
  → read_file(project file)
  → final response
  → trajectories.jsonl 有一条 used_skills=["repo-analysis"]
```

运行：

```bash
pytest tests/evolution/test_redaction.py tests/evolution/test_attribution.py tests/evolution/test_hook.py -q
ruff check nanobot/evolution tests/evolution
```

## 6. Day 3：PatchPolicy、Patch 应用与 Tool

预算：4 小时。

### 6.1 Policy

新增：

- `nanobot/evolution/policy.py`
- `tests/evolution/test_policy.py`

测试矩阵：

| 场景 | 预期 |
|---|---|
| 已有 Workspace Skill | 允许继续校验 |
| 内置 Skill | 拒绝 |
| 不存在 Skill | 拒绝 |
| Create/Delete | Schema 不提供 |
| `old_text` 出现一次 | 允许 |
| 出现零次/多次 | 拒绝 |
| Skill Name 改变 | 拒绝 |
| 无 Evidence | 拒绝 |
| 自动 Review 只有一条 Evidence | `no_change` 或 Tool 拒绝 |
| 两条 Evidence 来自同一 Turn | 拒绝 |
| 两条 Project Evidence 来自同一 Scope | 拒绝 |
| 两个不同 Turn/Project Scope 的同类缺陷 | 允许继续校验 |
| 手动 Review + 非空反馈 + 一条可验证 Evidence | 允许纠正例外 |
| 普通对话疑似纠正但未手动指定 | 不走单轨迹例外 |
| Duplicate Pending | 返回重复 |
| 绝对路径/Secret | 拒绝 |

### 6.2 Patching

新增：

- `nanobot/evolution/patching.py`
- `tests/evolution/test_patching.py`

实现：

- SHA-256；
- Preview Diff；
- Backup；
- Atomic Apply；
- Conflict；
- Restore。

### 6.3 Tool

新增：

- `nanobot/evolution/tool.py`
- `tests/evolution/test_evolution_tool.py`

实现：

- Patch-only Schema；
- 主 Agent Context 校验；
- Review Context 校验；
- Pending Proposal；
- Runtime Context Provider。

### Day 3 验收

- Tool 无任何直接 Apply 路径；
- 内置 Skill 测试明确失败；
- Approve 前 `SKILL.md` 不变；
- Conflict 时不覆盖；
- Restore 能回到旧内容。

## 7. Day 4：Review Agent 与调度 Service

预算：4 小时。

### 7.1 Review Agent

新增：

- `nanobot/evolution/prompts.py`
- `nanobot/evolution/reviewer.py`
- `tests/evolution/test_reviewer_contract.py`

实现：

- 独立 ToolRegistry；
- `review_evidence`；
- `skill_manage`；
- Runtime 解析；
- 8 Iterations；
- 60 秒 Timeout；
- 一个 Proposal；
- `no_change`；
- Error/Timeout 状态。

不创建 Provider Stub。Tool 白名单、Runtime 选择前置校验、Timeout 包装和 Proposal 状态使用不调用模型的纯逻辑测试；完整 `AgentRunner → 模型 → skill_manage` 路径使用真实 API 集成测试。

### 7.2 Service

新增：

- `nanobot/evolution/service.py`
- `tests/evolution/test_evolution_service.py`

实现：

- 活动 Trace Registry；
- Record；
- 按配置每 5/10/20/100 条触发，默认 10；
- 失败立即触发；
- 独立 Evidence 分组；
- 不同 `turn_id` 校验；
- Project Scope Hash 校验；
- 手动纠正例外；
- 多 Skill 不自动触发；
- 每 Skill 一个 Active Review；
- `review_pending` 合并；
- Proposal 通知。

### Day 4 验收

```text
默认策略：第 9 条成功轨迹 → 不触发
默认策略：第 10 条成功轨迹 → 触发一次
5 次策略：第 5 条成功轨迹 → 触发一次
Review 运行中新增触发 → 不并发，标记 Pending
Review 完成 → 最多补跑一次
单条失败轨迹 → 立即触发 Review，但证据不足时 no_change
第二个不同任务出现同类缺陷 → 允许 Proposal
同一任务内反复重试 → 仍只算一条 Evidence
手动非空反馈 + 一条可验证轨迹 → 允许 Proposal
多 Skill 失败 → 不自动触发
```

## 8. Day 5：Bootstrap、命令与端到端闭环

预算：4 小时。

### 8.1 AgentLoop 扩展接口

修改：

- `nanobot/agent/loop.py`

新增：

- `register_hook_factory()`；
- `schedule_background()`；
- `from_config()` 调用 Bootstrap。

先增加针对默认关闭的回归测试。

### 8.2 Bootstrap

新增：

- `nanobot/evolution/bootstrap.py`
- `tests/evolution/test_bootstrap.py`

验证：

- Disabled 零注册；
- Enabled 注册一个 Hook Factory；
- Tool 注册一次；
- Command 注册一次；
- 多次安装幂等。

### 8.3 Commands

新增：

- `nanobot/evolution/commands.py`
- `tests/evolution/test_evolution_commands.py`

覆盖：

- Status；
- Review；
- Approve；
- Reject；
- Restore；
- 缺少参数；
- 无效 ID；
- Conflict；
- Disabled。

### 8.4 Integration

集成覆盖分布在：

- `tests/evolution/test_bootstrap.py`
- `tests/evolution/test_evolution_service.py`
- `tests/evolution/test_evolution_commands.py`

端到端：

```text
from_config(enabled)
  → 正常 Turn 读取 repo-analysis
  → Trace
  → 自动 Review
  → Pending Proposal
  → /evolve 展示
  → approve
  → 下一次 Context 含新版 Skill
  → restore
```

### Day 5 验收

- 原 WebUI 不改也能发送全部命令；
- 普通回复不等待 Review；
- Review 失败不影响普通回复；
- Disabled 时与原版一致。

## 9. Day 6：真实 Python 仓库实验

预算：4 小时。

### 9.1 Demo Skill

实际新增：

```text
experiments/nanoevo/repo-analysis.SKILL.md
```

初始 Skill 保持合理、简单，不故意写明显错误。它应指导：

- 检查元数据；
- 识别包；
- 识别 Entry Point；
- 识别测试；
- 用文件路径支撑结论；
- 区分事实与推断。

### 9.2 Benchmark 工具

实际新增：

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

`run_experiment.py`：

- Clone 三个公开 Python 仓库并校验固定 Commit SHA；
- 拒绝复用脏仓库和非全新的实验 Workspace；
- 使用真实 API；
- 在真实任务中运行；
- 保留不同 `turn_id`，`project_scope_hash` 仅用于来源审计；
- 证明同一缺陷至少出现两次后才允许 Proposal；
- 只有显式 `--approve` 才预授权应用一个合理 Proposal；
- Held-out Repo 分别使用 Baseline/Evolved Skill；
- 保存原始模型回答、Token、Tool Calls、停止原因和错误；
- 用固定 Required Terms 与真实路径存在性产生确定性 JSON 指标。

固定仓库：

| 角色 | 仓库 | Commit |
|---|---|---|
| Experience 1 | `pallets/itsdangerous` | `672971d66a2ef9f85151e53283113f33d642dabd` |
| Experience 2 | `pallets/click` | `00e592cea702e0b2caa0dee42489fdb1c22cd845` |
| Held-out | `pallets/markupsafe` | `b2e4d9c7687be25695fffbe93a37622302b24fb1` |

### 9.3 实验纪律

- 同一模型；
- 同一 Temperature；
- 同一任务 Prompt；
- 同一 Held-out Commit；
- 唯一变量是 Skill 版本；
- API Key 走环境变量；
- 不手改 Agent 输出；
- 不编造结果；
- 结果不好也如实记录并分析。

### 9.4 真实结果（单次受控案例）

| Held-out：`pallets/markupsafe` | Baseline | Evolved | 变化 |
|---|---:|---:|---:|
| 仓库路径引用准确率 | 77.8% | 93.3% | +15.6 个百分点 |
| 必需信息召回率 | 100.0% | 83.3% | -16.7 个百分点 |
| Tool Calls | 19 | 25 | +6 |
| Total Tokens | 145,361 | 304,555 | +159,194 |

Review 从两个 Experience 轨迹中发现重复的“仅引用裸文件名”问题，只修改
现有 `repo-analysis` Skill 的一行约束，将其收紧为仓库根目录相对路径。Proposal
先保持 Pending，再经审批应用，且 Apply 前生成历史备份。

该结果证明了进化闭环能够运行，并显示路径可解析性提高；它也暴露了更高成本与
信息召回下降。由于只有一个 Held-out 仓库、单模型单次采样，不能据此声称普遍提升。

### Day 6 验收

- 三个仓库 Commit 已锁定；
- 至少一次完整真实 API 实验；
- Held-out Repo 未参与 Skill 进化；
- 报告可一条命令重现。

## 10. Day 7：全量验证、文档和简历材料

预算：4 小时。

### 10.1 完整验证

依次运行：

```bash
ruff check nanobot/ experiments/nanoevo tests/evolution tests/config/test_evolution_config.py
pytest tests/evolution tests/config/test_evolution_config.py -q
pytest tests/agent/test_turn_hooks.py tests/agent/test_skills_loader.py tests/agent/test_loop_runner_integration.py -q
pytest
```

只对新增文件运行 `ruff format --check`；不批量格式化上游原文件，避免产生无关 Diff。

如果全量测试耗时过长：

1. 必须完成 Evolution 测试；
2. 必须完成受影响回归测试；
3. 全量测试允许后台运行，但最终必须读取结果。

### 10.2 文档

修改：

- `README.md`
- `docs/configuration.md`
- `docs/chat-commands.md`
- `docs/architecture.md`

README 项目章节：

1. Motivation；
2. Before/After；
3. Architecture；
4. Safety Boundary；
5. Demo；
6. Experiment；
7. Results；
8. Limitations；
9. Reproduce。

### 10.3 Demo

录制 2–3 分钟：

1. 原 nanobot 执行仓库分析；
2. 展示保存的轨迹；
3. 自动 Review；
4. `/evolve` 查看 Proposal；
5. Approve；
6. 新任务加载新版 Skill；
7. Restore。

### 10.4 简历材料

准备：

- 一句项目定位；
- 两条技术贡献；
- 一条实验结果；
- 一张架构图；
- 一个 GitHub README；
- 三个面试问题的答案：
  - 为什么不用 Memory？
  - 为什么不能自动 Apply？
  - 为什么 Hook 不改 Runner？

## 11. 测试覆盖矩阵

| 能力 | 单元 | 集成 | 真实实验 |
|---|---:|---:|---:|
| Config | 是 | 是 | 否 |
| Trace | 是 | 是 | 是 |
| Redaction | 是 | 是 | 否 |
| Skill Attribution | 是 | 是 | 是 |
| Review Trigger | 是 | 是 | 是 |
| Evidence Independence | 是 | 是 | 是 |
| Manual Correction Exception | 是 | 是 | Demo |
| Review Agent | 纯逻辑边界测试，不使用 Fake Provider | 真实 API | 真实模型 |
| Patch Gate | 是 | 是 | 是 |
| Approve/Reject | 是 | 是 | Demo |
| Hash Conflict | 是 | 是 | 否 |
| Restore | 是 | 是 | Demo |
| 内置 Skill 保护 | 是 | 是 | 否 |
| Disabled 回归 | 是 | 是 | 否 |
| Skill 改进效果 | 否 | 否 | 是 |

## 12. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| Review 容易给主观修改 | Skill 污染 | 证据门禁、`no_change`、人工审批 |
| 一次失败错误归因 | 无效 Patch | 单 Skill 自动归因、多 Skill跳过 |
| 同一任务重复失败被误算成多条证据 | Skill 污染 | 按 `turn_id` 去重 |
| 同一仓库特例被误当成通用规则 | 过拟合 | Project Scope Hash 和 Held-out Repo |
| Prompt Injection | 长期规则污染 | 受限工具、确定性校验、审批 |
| Review 阻塞回复 | 用户体验下降 | `after_run` 只调度后台任务 |
| 模型成本过高 | 实验难复现 | 10 条窗口、最多 8 轮、独立 Preset |
| 上游代码改动过大 | 一周做不完 | 只改 Config 和 Loop 装配 |
| 实验提升不明显 | 简历证据弱 | 如实展示 Failure Analysis，不伪造提升 |
| 文件写坏 | Skill 不可用 | 原子写、Backup、Frontmatter 校验 |
| 用户同时编辑 Skill | 覆盖修改 | Base Hash Conflict |
| 轨迹泄密 | 安全问题 | 持久化前递归脱敏和截断 |

## 13. 每日停止条件

每天结束前必须满足：

1. 当天新增代码有对应测试；
2. 当天测试通过；
3. Ruff 无新增错误；
4. 没有调试输出和未解释 TODO；
5. 没有修改用户无关文件；
6. 记录下一天唯一首要任务。

如果当天失败：

- 不扩展下一模块；
- 先修复当前垂直切片；
- 不用跳过测试换取“进度”。

## 14. 最小可交付版本与删减顺序

必须保留：

- Config；
- Hook；
- Trace；
- 单 Skill Attribution；
- 自动 Review；
- `no_change`；
- Patch Proposal；
- Approve/Reject；
- Built-in Protection；
- Hash Conflict；
- Restore；
- 一个真实 Held-out 实验。

可优先删减：

1. 精美通知格式；
2. `/evolve` 的统计细节；
3. 不增加第三个 Experience Repo，但必须保留两个独立 Evidence Repo；
4. 第二个示例 Skill；
5. 新 WebUI 页面；
6. 可配置阈值。

## 15. 最终 Definition of Done

代码：

- [x] 新业务集中在 `nanobot/evolution/`
- [x] `AgentRunner` 未修改
- [x] `SkillsLoader` 未修改
- [x] WebUI 未修改
- [x] 无新依赖
- [x] 默认关闭

功能：

- [x] 正确识别 Workspace Skill 使用
- [x] 最近 10 条轨迹 Review
- [x] 客观失败立即 Review
- [x] 自动 Proposal 需要两个不同 Turn
- [x] Project Evidence 需要不同 Scope
- [x] 手动非空反馈可走单轨迹例外
- [x] Review 可 `no_change`
- [x] 只能 Patch 已有 Workspace Skill
- [x] 内置 Skill 不可修改
- [x] 人工批准后才 Apply
- [x] Conflict 不覆盖
- [x] Restore 可用

质量：

- [x] Evolution 单元和集成测试通过
- [x] 受影响的原测试通过
- [x] 最终全量测试结果已读取：`5273 passed, 17 skipped`
- [x] Ruff 通过
- [x] Secret 不进入轨迹

项目展示：

- [x] 真实仓库和真实 API
- [x] Commit 固定
- [x] Held-out 对比
- [x] README 有结果和限制
- [x] Demo 脚本可复现
- [x] 简历描述不夸大为模型训练
