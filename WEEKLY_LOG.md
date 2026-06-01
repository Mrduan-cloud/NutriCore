# WEEKLY_LOG · NutriCore

> 每周复盘。Phase 1（90 天开局冲刺）按周轮转，周日把本周 `.scratch/daily-*` 汇总到这里。
> 本仓库是离职后基于公开技术栈重新 mock 的开源版本，不含任何前东家真实业务数据。

---

## W01 · 2026-05-25 → 2026-05-31 · LangGraph 主控跑通（headliner 开局）

> 对应简历：「AI 营养师 Agent · LangGraph 多 Agent 编排 · 意图识别 → 子 Agent 路由」

### 这周做了什么

| 日期 | commit | 内容 |
|---|---|---|
| 5/25 Day1 | `ce860d4` / `bcf81a1` | 给远端已有但**零测试**的 6 节点 graph 补 18 个 happy-path 测试；测试过程暴露 **3 个 LangGraph noop-write 真 bug**（节点返回空 dict 在 0.0.40+ 抛 `InvalidUpdateError`，证明这些代码静态写好但**从没跑过端到端**）；self-review 又挖出 2 个 Critical——Prometheus label 用 LLM 原始输出（无界 series 风险）→ 白名单收敛；异常细节漏进用户文案 → 脱敏 |
| 5/27 Day3 | `d60637f` / `2fbf7df` | intent_router 插入**规则 + LLM 双轨**意图分类（确定性短语绕过 LLM，省 ~200ms/~150token，含 NFKC 全角归一化）；self-review 修掉**多模态消息绕过高风险 gate** 的安全 issue（`content` 为 `list[dict]` 时子串检查恒 False，"建议就医"会被前端 SDK 升级悄悄绕过） |
| 5/29 Day5 | `cbe7d9c` | **Redis 短期记忆（最近 6 轮）**：按 `(用户, 会话)` 用 Redis List 滚动存（RPUSH + LTRIM + 2h TTL），多轮筛查改由服务端有状态维护，不再依赖前端回传 history；所有 Redis 异常降级为"无记忆"而非 500；8 个离线单测（内存 FakeRedis） |
| 5/30 Day6 | `6442a6d` / `5eb3f95` | 修 4 个 stale 图测试 + 纳入 CI；测试回归挖出方案 Agent 引用分隔符 `#` vs `:` 真 bug；根因修掉**连红 3+ 次无人察觉的 CI**（pin `ruff==0.15.15` 止漂移、补 fastapi、锁 `marshmallow<4` 规避 pymilvus→environs 4.0 不兼容），干净镜像模拟 CI 验证 52 测试全绿 |

### ⚠️ 本周重大偏离：HR 触发的 demo 冲刺

本周中段，HR 询问「有无可线上演示的作品」，临时插入一波 **demo 冲刺**（16+ commit，`990bab4…c1b488b`），交付了一个**可登录、可对话、可演示**的完整版本。这波冲刺**跳过了 plan 的周次顺序**，提前实现了原本排在 W04 / W10 / W11 的工作，并新增了大量 plan 里压根没有的能力：

- **提前于 plan 完成**：确定性 NRS-2002 评分（原 W04，6/15）、NL2SQL→ECharts 数据洞察 + 4 段式洞察报告（原 W10，7/27）、Docker compose 全栈部署跑通（原 W11 的一部分，8/3）
- **plan 完全没有、却已交付**：多用户 bcrypt 鉴权 + RBAC + admin 后台、Vue3 + Vite 前端（登录 / 对话 / 公开分享页）、SSE 流式打字机、Perplexity 风格 UI + 多 Agent 调度链可视化、真分享链接（snapshot + token + 公开页）、反馈→审计闭环、术语 hover 释义、全套 SVG 图标

**态度**：HR 一句"有无 demo"是直接转化机会，值得插队——但插完要归位。5/29 已把当日 plan 任务（Redis 记忆）补回、把 demo 积压一并 push；本周报如实记录这次偏离，并据此在 6/1 把 90 天计划重排为 v4（NutriCore 已严重超前，压缩其占比、把精力前移给停滞的 MediRead / MemoMate）。

### 收获

1. **不在 CI 里的测试 = 会腐烂的测试**：6 节点 graph 测试早写好但因依赖重没进 CI，demo 期一改实现就 stale 没人知道。纳入 CI（配 pin 依赖）才是真正止血。
2. **静默红 CI 是系统性风险**：连红 3+ 次没人看，后续步骤根本没跑过。每次推完看一眼 CI 该是肌肉记忆。
3. **远端代码完整 ≠ 跑过**：3 个 noop-write bug 说明只有测试是真正的可执行证明。
4. **开工三连查 + commit 后立即 self-review** 已成肌肉记忆：本周 5/25 / 5/27 各靠 self-review 抓到一个 Critical。
5. **plan 与现实的张力是常态**：机会主义插队（demo 冲刺）是对的，但要记得归位 + 如实复盘，别让主线断档。

---
