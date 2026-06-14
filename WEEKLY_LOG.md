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

## W05 · 2026-06-22 → 2026-06-28 · 主项目（NutriCore 已建能力固化）

> 对应简历：「AI 营养师 Agent」全栈四能力——本周把 demo 冲刺期**建好但没测/没文档**的能力补成测试 + 文档 + 缺口闭合。
> 本周角色：NutriCore 当主项目（6/22 / 6/24 / 6/26 / 6/27），MediRead / MemoMate 周二 / 周四轮值。
> 主题：让「能跑的 demo」变成「能背书简历、面试敢逐个 demo」。完成驱动，本节按 plan 标称日期归档。

### 这周做了什么

| 日期 | 项目 · PR | 内容 |
|---|---|---|
| 6/22 | NutriCore `#27` | meal_plan **生成端到端 + 引用接地**：`test_meal_plan_generator`（monkeypatch retrieve+LLM，证据引用必带 KB 来源、无依据即拒）进 CI；`test_meal_plan_e2e_live` 容器内实跑 7 天方案 / 74 条引用全接地。顺手让 generator 复用 `mifflin_st_jeor_bmr_raw`，消掉一处 BMR 估算重复 |
| 6/23 | MediRead `#25` | **指标别名归一化**（轮值）：`_norm_key`（NFKC + casefold + 连字符统一）+ `aliases_for` 双向查；`synonyms.json` 由 ~27 扩到 ~50（中文旧称 ↔ 标准名，GGT ↔ γ-谷氨酰转移酶），脏 OCR 鲁棒 |
| 6/24 | NutriCore `#28` | risk_screening **PDF 渲染 + MinIO 归档核验**（补 W04 缺口）：`render_pdf(NRSReport)→bytes` 与 MinIO **解耦**——纯渲染（中文字体 / 三档配色分支）进 CI，`archive_report → presigned_url` 往返作 skip-guard live 测试；容器内实测 3683B PDF 往返 |
| 6/25 | MemoMate `#14`(+`#15`) | **github_trending** server（轮值）：stdlib 零依赖爬 github.com/trending，`get_github_trending(language, since, limit)`，稳定锚点解析 + `_RateLimiter`；实网验证 Python 周榜 top-3 解析正确。`#15` 回填两份 README 服务索引、删陈旧 weather 行 |
| 6/26 | NutriCore `#29` | data_insight **NL2SQL 三层隔离审计 + 加固**：审计 `assert_safe_sql` 挖出 3 处真口子并修——① 字段白名单是**死代码**(`ALLOWED_FIELDS` 从未被用) → 改逐标识符校验、禁裸 `SELECT *`；② `... user_id='我' OR 1=1` 整段绕过强制过滤 → 禁 `OR`、过滤改正则锚到本人 id；③ `UNION SELECT … user_id='他人'` 跨用户读 → 禁 UNION/子查询/注释/危险函数。测试 5 → 30 条，按 Layer1/2/3 分组 |
| 6/27 | NutriCore `#30` | docs：4-Agent 架构图 ASCII → **Mermaid**（GitHub 原生渲染，标清主控 + 三子 Agent 拓扑）；特性清单**对齐真实实现**——NL2SQL 改如实表述（无 Vanna 依赖，标为生产可平替）、数据隔离要点扩写为审计级三层收口 |

### 现状

- ✅ 四大能力全部「固化」：筛查（NRS2002 + PDF 往返核验）、方案（RAG e2e + 引用接地）、洞察（NL2SQL 三层隔离审计级加固）、主控（W01 已固化）——每条都有 CI 纯逻辑测试 + skip-guard live 双层守护。
- ✅ NutriCore README 与代码不再有口径差（Vanna 过度声称已纠正），4-Agent 架构图可在 GitHub 直接看图。
- 🟡 跟进任务仍挂着：medical_kb 上 Cross-Encoder 负增益待 KB 规模化复评（W04 起的 background task）。
- 🟡 W02 retro 三仓仍缺（非阻塞，补则补在当周主项目仓）。

### 收获

1. **「补测」常常就是「补 bug」**：6/26 名义是给 `test_nl2sql_safety` 补强,认真重读实现才发现字段白名单是死代码、还有两条跨用户泄露路径。和 W04「灌完库必须复验」一个道理——**写测试/文档的过程本身就是最便宜的代码审计**,真去读才看得见。
2. **安全设计敢于「收窄」**：单用户分析查询本就不需要 `OR` / 子查询 / `UNION`,放开任何一个都是越权口子。与其用解析器追求「什么都支持还安全」,不如 fail-closed 砍掉用不到的能力——这个取舍写进了代码注释和文档,面试能讲清「为什么禁 OR」。
3. **文档诚实化是固化的一部分**：README 把 NL2SQL 写成「Vanna.ai」,但 `requirements.txt` 根本没这依赖。延续 W01「简历真实性 > 丰满度」、W04「诚实负结果 > 假增益」——把口径拉回实现,Vanna 标成生产平替路径,interviewer 深扒也站得住。
4. **解耦让重能力也能进 CI**：`render_pdf` 与 MinIO 拆开后,纯渲染（字体/配色/拼装）能在 CI 跑,真往返留给 live。和 W04 的评测分层同一套打法——重依赖不是「测不了」的借口。

### 下周预告 · W06（06/29–07/05）· MemoMate servers 扩充

主项目切到 **MemoMate**：`hackernews` / `wechat_mp`(httpx + selectolax) / `12306` 任选 2–3 个落地 + `SERVERS.md`（每 server 一行 + 3 个示例 prompt）。轮值穿插 NutriCore 画像字段、MediRead joint_analysis 起步。

---
