# NanoEvo Skills 进化管理 WebUI 执行计划

> 状态：Completed（2026-07-26）
> 工作类型：Brownfield 增量开发
> 预计投入：12–16 小时（3 天 × 4 小时，另留 2–4 小时验证与简历材料整理）
> 前置文档：[UI 设计](./ui-design.md) · [功能与接口设计](./functional-api-design.md)

## 1. 执行目标

在不改变 nanobot 原有 Agent、Skills 加载和 WebUI 导航逻辑的前提下，为 NanoEvo 增加一个可视化控制面，使用户可以：

- 看见全局进化开关和运行状态。
- 看见哪些 Skill 可进化、哪些受保护，以及自动复盘进度。
- 查看最近 10 次脱敏证据并请求复盘。
- 审核、批准或拒绝修改提案。
- 比较任意两个保留版本，并切换到指定版本。

完成后应能演示完整故事：

```text
Workspace Skill 被真实任务使用
→ 自动积累轨迹
→ 达到条件或用户请求复盘
→ 主模型/可切换模型生成修改提案
→ 用户在 WebUI 查看证据和 Diff
→ 批准后安全修改 SKILL.md 并备份
→ 后续任务使用改进后的 Skill
→ 必要时比较并切换到历史版本
```

## 2. 已确认需求

- Skill 自进化是项目主线，不做独立 Agent 评测平台。
- 只改进已有 Skill，不创建全新 Skill。
- 只允许 Workspace Skills 进化；Built-in Skills 永久保护。
- 使用真实 Python 仓库任务和真实模型，不做 fake provider 实验。
- 自动收集轨迹、自动触发复盘、人工批准应用。
- 周期复盘可选每 5/10/20/100 次可归因使用触发，默认 10 次。
- 自动复盘观察最近 10 次轨迹。
- 复盘默认复用主模型，并允许通过 `reviewModelPreset` 切换。
- 不强制每次复盘都必须提出修改，允许 `no_change`。
- 历史永久保存，V1 采用最简单可靠的本地文件存储。
- WebUI 尽量少改原代码，延续现有 Skills 页面风格。

## 3. 不做什么

- 不新增 Sidebar 页面或顶级路由。
- 不修改 `AgentRunner` 和 `SkillsLoader`。
- 不改变 NanoEvo Hook、Reviewer、Policy、Patcher 的既有职责。
- 不增加前端或后端依赖。
- 不把开关伪装成运行时热切换。
- 不引入 WebSocket 实时事件。
- 不开放任意文件编辑。
- 不展示模型 Chain-of-Thought。

## 4. 文件变更矩阵

### 新增文件

| 文件 | 责任 |
|---|---|
| `nanobot/evolution/webui.py` | 安全 DTO、总览/详情聚合、动作路由 Controller |
| `tests/evolution/test_webui.py` | Evolution WebUI 后端契约测试 |
| `webui/src/components/settings/SkillEvolutionSheet.tsx` | Sheet 外壳、全局状态、移动端导航 |
| `webui/src/components/settings/SkillEvolutionPanel.tsx` | Skill 概览、提案、版本三个页签 |
| `webui/src/hooks/useSkillEvolution.ts` | 请求、轮询、刷新、异步状态 |
| `webui/src/tests/skill-evolution-sheet.test.tsx` | 组件与交互测试 |

### 修改文件

| 文件 | 最小修改 |
|---|---|
| `nanobot/cli/commands.py` | 将 `agent.skill_evolution` 传入 ChannelManager |
| `nanobot/channels/manager.py` | 增加可选 service 参数并转交 |
| `nanobot/webui/gateway_services.py` | 将可选 service 注入 HTTP handler |
| `nanobot/webui/ws_http.py` | 初始化并调用可选 Evolution 子路由 |
| `webui/src/components/settings/SkillsCatalogSettings.tsx` | 增加“进化管理”按钮和 Sheet |
| `webui/src/lib/api.ts` | 增加 Evolution 查询和动作 API |
| `webui/src/lib/types.ts` | 增加响应、状态和动作类型 |
| `webui/src/tests/api.test.ts` | API URL、Header 与错误测试 |
| `webui/src/tests/skill-evolution-sheet.test.tsx` | Skills 页面入口、焦点、轮询和危险动作回归测试 |

### 明确不修改

```text
nanobot/agent/runner.py
nanobot/agent/skills.py
nanobot/evolution/hook.py
nanobot/evolution/reviewer.py
nanobot/evolution/policy.py
nanobot/evolution/patching.py
webui/src/App.tsx
webui/src/globals.css
webui/package.json
pyproject.toml
```

若实现过程中发现必须修改上述文件，先记录原因并重新审视边界；不能为了省事把 UI 逻辑塞入 Agent 核心。

## 5. 分阶段任务

### Phase 0：锁定现有行为（1 小时）

目标：证明改动前 Agent、NanoEvo 和 Skills WebUI 都正常。

任务：

1. 运行现有 Evolution 单元测试。
2. 运行现有 WebUI API 和 Skills 页面测试。
3. 记录 Skills API 当前返回结构。
4. 确认 NanoEvo 禁用时 `AgentLoop.skill_evolution` 的实际值。
5. 为即将修改但缺少保护的行为补最小回归测试。

完成门：

- 现有相关测试通过。
- 测试能证明禁用 NanoEvo 时 Skills 页面不依赖进化服务。

### Phase 1：后端只读 Facade（2–3 小时）

目标：先完成总览和详情，不做任何动作接口。

任务：

1. 新建 `EvolutionWebUIController`。
2. 复用 `SkillsLoader` 获取完整 Skill 清单和来源。
3. 复用 `PatchPolicy` 判定 Workspace Skill 资格。
4. 聚合 `SkillReviewState`、Pending Proposal、Version Records。
5. 实现安全的最近 10 条轨迹摘要。
6. 实现：
   - `GET /api/webui/evolution`
   - `GET /api/webui/evolution/skills/{name}`
7. 增加认证、404、禁用状态测试。

完成门：

- Built-in 全部是受保护状态。
- Workspace Skill 进度与 Store 一致。
- 响应中找不到绝对路径、密钥、`chat_id`、`session_key` 或完整工具结果。

### Phase 2：服务注入与动作接口（2–3 小时）

目标：所有写操作只通过现有 Service 完成。

任务：

1. 从 `AgentLoop.skill_evolution` 向 Gateway 传递可选 Service。
2. 实现配置保存接口并返回 `restart_required`。
3. 实现请求复盘、批准、拒绝、版本比较和切换接口。
4. 将 Service/Policy 异常映射为稳定错误码。
5. 验证批准仍执行 base hash、证据门禁、原子写和备份。

完成门：

- Controller 没有直接写 `SKILL.md` 或 Evolution Store。
- NanoEvo 禁用时 Gateway 和原 Skills API 不受影响。
- Built-in 即使绕过前端调用接口仍无法被修改。
- 冲突时不会覆盖用户编辑。

### Phase 3：前端 Sheet 与只读状态（2–3 小时）

目标：先让状态可见，再接危险动作。

任务：

1. 定义 TypeScript DTO。
2. 在 `api.ts` 增加总览和详情请求。
3. 实现 `useSkillEvolution` 的加载、错误、刷新状态。
4. 在 Skills 页标题区加入“进化管理”按钮。
5. 实现 Sheet：
   - 全局配置/运行状态
   - Skill 筛选和列表
   - Protected/Evolvable/Collecting/Reviewing/Pending 状态
   - 桌面双栏和移动端两层导航
6. 实现概览、进度和证据缺口。

完成门：

- 不改 App 路由即可打开/关闭 Sheet。
- 当前演示环境能够呈现 13 个 Skills，其中 2 个可进化、11 个受保护。
- 320px 宽度无页面级横向滚动。

### Phase 4：复盘、提案与版本动作（3–4 小时）

目标：完成端到端管理闭环。

任务：

1. 接入配置开关和模型 Preset 选择。
2. 接入“请求复盘”和可选反馈。
3. Reviewing 时每 2 秒轮询，结束即停止。
4. 实现提案原因、证据门禁、文本 Diff。
5. 为批准、拒绝和版本切换增加确认 Dialog。
6. 动作成功后同时刷新总览和详情。
7. 处理 `409` 冲突、`422` 门禁、`503` 未启用、`504` 超时。

完成门：

- 请求复盘不会直接修改 Skill。
- 批准后产生备份且 Proposal 状态为 `applied`。
- 拒绝后不能再次批准同一 Proposal。
- 可以比较任意两个保留版本；切换前备份当前版本并要求确认。

### Phase 5：质量、验证与文档（2 小时）

任务：

1. 补齐键盘、焦点、ARIA 和 reduced-motion。
2. 检查 Light/Dark 模式。
3. 检查 320、390、768、1440px。
4. 运行 lint、测试和 WebUI build。
5. 用真实 Workspace Skill 完成一次请求复盘到批准/恢复的演示。
6. 截图并记录简历可量化结果：
   - 轨迹数量
   - 复盘耗时
   - 证据门禁
   - Proposal 数量
   - 成功应用与恢复

完成门：

- 原功能回归通过。
- 新功能验收矩阵全部通过。
- 文档与实际 API 字段一致。

## 6. 测试与验证命令

按依赖顺序执行：

```bash
.venv/bin/ruff check nanobot/ tests/
.venv/bin/pytest tests/evolution -q
.venv/bin/pytest -q

cd webui
bun run test
bun run build
```

文档或 UI 截图不能替代真实模型验证。端到端演示使用用户配置的真实 API Provider；测试中可以通过注入已构造的 Service/Store 隔离网络，但不能用 fake provider 伪造简历实验结果。

## 7. 验收矩阵

| 场景 | 预期 |
|---|---|
| NanoEvo 关闭 | 原 Skills 页面正常；Sheet 可解释开启方式；动作不可执行 |
| 配置开启但未重启 | 显示“配置已开启 / 当前未运行 / 需要重启” |
| 11 个 Built-in Skills | 全部受保护，无复盘、批准或恢复动作 |
| 2 个 Workspace Skills | 显示可进化状态和各自进度 |
| 7/10 条轨迹 | 显示还差 3 条，不伪装成已满足条件 |
| 单条真实归因轨迹 | 可以参与复盘，不要求独立任务轮次或独立项目 |
| 带反馈手动复盘 | 反馈帮助 Reviewer 聚焦，但不能替代真实轨迹 |
| 复盘无改进必要 | 显示 `no_change`，不强制生成 Proposal |
| 复盘生成提案 | 展示原因、证据、Diff，等待人工决定 |
| 批准 | 先备份，再原子应用，刷新版本 |
| Skill 被外部修改 | 返回冲突，不覆盖 |
| 拒绝 | Proposal 变为 rejected，Skill 不变 |
| 切换历史版本 | 当前内容先备份，再原子切换到指定版本 |
| 复盘超时 | UI 恢复可操作状态并保留错误 |
| 320px 移动端 | 无横向溢出，操作目标不小于 44px |

## 8. 实施结果

本计划已按既定边界完成，实际落地结果如下：

- 在原 `Settings → Skills` 页面加入 `Evolution management` 入口，通过右侧
  Sheet 管理，不新增路由或导航。
- 后端新增认证后的薄 Facade，查询只读 Store，所有复盘、批准、拒绝和恢复动作
  都复用 `SkillEvolutionService`。
- Built-in Skills 在前后端均永久只读；只有 Workspace Skills 可以请求复盘或被修改。
- 最近证据限制为 10 条，并移除绝对路径、密钥、会话标识和完整工具输出。
- 配置保存后明确区分 `enabled`、`runtime_active` 和 `restart_required`，没有实现
  虚假的热切换。
- Reviewing 状态每 2 秒轮询；复盘结束后自动停止。
- 提案批准、拒绝和版本切换均有确认 Dialog；批准仍经过证据门禁、base hash、
  备份和原子写保护。
- 未修改 `AgentRunner`、`SkillsLoader`、`App.tsx`、全局样式或依赖清单。
- 真实模型闭环实验已记录在
  [`experiments/nanoevo/README.md`](../../experiments/nanoevo/README.md)：
  Reviewer 基于两个真实 Python 仓库轨迹改进已有 `repo-analysis` Skill，并在固定
  held-out 仓库上将路径引用落地率从 77.8% 提升到 93.3%；同时如实记录了覆盖率
  和成本回退，未将单次实验包装成普遍提升。

最终验证（2026-07-26）：

```text
Python ruff:       passed
Python focused:    55 passed
Python full suite: 5279 passed, 17 skipped
WebUI lint:        passed
WebUI tests:       49 files, 717 tests passed
WebUI build:       passed
git diff --check:  passed
```

全量 Python 测试在 macOS 上需清除包含裸 IPv6 `::1` 的代理环境变量，避免当前
httpx 将其误解析为端口。最终验证命令使用干净代理环境运行，未屏蔽或跳过失败用例。
| 暗色模式 | 状态、Diff、错误均清晰可读 |

## 8. 风险与应对

| 风险 | 应对 |
|---|---|
| 用户以为开关立即生效 | 分开展示配置和运行状态，明确需要重启 |
| 重复或无关证据 | 要求至少一条持久化、可归因且指向目标 Skill 的真实轨迹 |
| 复盘耗时较长 | 异步请求、局部轮询、超时后可重试 |
| Proposal 生成后 Skill 被手动编辑 | base hash 冲突保护，要求重新复盘 |
| 轨迹泄露路径或密钥 | 复用 redaction，仅返回有限摘要，增加泄露回归测试 |
| UI 与 Store 状态漂移 | 动作后强制 refetch，UI 不乐观伪造 Proposal 状态 |
| 原 WebUI 被进化服务绑死 | 所有注入均可选，子路由不可用时原路由不变 |
| 切换版本覆盖当前内容 | 切换前自动备份当前版本，并使用完整哈希限定目标 |

## 9. 回退方案

这项改动应能按层回退：

1. 移除 Skills 页按钮和新前端组件，原 Skills 页恢复原样。
2. 移除 Evolution 子路由，其他 WebUI API 不变。
3. 移除可选 Service 注入参数，AgentLoop 和 NanoEvo 核心不变。
4. 已保存的 `.nanobot/evolution` 数据和 Skill 版本不删除，可继续通过命令使用。

不通过删除用户 Workspace Skill、Evolution 历史或备份来回退。

## 10. 关键决策记录

| 方案 | 决定 | 原因 |
|---|---|---|
| 新增顶级导航页 | 拒绝 | 功能属于 Skills 管理，增加路由改动和认知负担 |
| Skills 页右侧 Sheet | 采用 | 与现有详情交互一致，改动最小 |
| 运行时热启停 | V1 拒绝 | Hook 在 AgentLoop 构造时安装，伪热切换会制造状态不一致 |
| UI 直接读写文件 | 拒绝 | 绕过 Policy、备份、hash 冲突与原子写 |
| WebSocket 实时推送 | V1 拒绝 | 2 秒局部轮询足够，避免协议扩张 |
| 任意保留版本比较与切换 | 采用 | 面向内容哈希选择目标，切换前备份当前版本 |
| 新 UI/状态依赖 | 拒绝 | 现有 React、Radix/shadcn、Tailwind 已足够 |

## 11. 实现完成定义

只有同时满足以下条件才算完成：

- 功能矩阵通过。
- Python lint、Evolution 测试、全量测试通过。
- WebUI 测试和生产构建通过。
- 禁用 NanoEvo 时原 Agent、原 Skills 页面和 Gateway 行为不变。
- 内置 Skills 无论通过 UI 还是直接请求都不可修改。
- 完成至少一次真实模型、真实 Workspace Skill 的复盘—批准—版本切换演示。
- README/设计文档中的接口、限制和截图与实际实现一致。
