# ADR-0001: 用 LangGraph 编排 AI 营养师主控

- 状态：Accepted
- 日期：2026-06-02

## 背景 (Context)

AI 营养师是 NutriCore 的主控 Agent，需要把用户**一句话**可靠地导向正确的处理路径：

- **意图路由**：把咨询分发到 4 个子能力之一（营养风险筛查 / 个性化营养方案 / 健康数据洞察 / 一般咨询）。
- **高风险短路**：用药 / 急重症 / 孕产期等问题必须**绕过**正常链路，直接走 `safety_fallback`（"建议就医"）。
- **多轮记忆 + 用户画像**：跨轮维护上下文（Redis 短期）与画像实体。
- **引用核验**：方案 / 咨询的输出引用必须能映射回知识库，杜绝"无依据胡编"。

对编排层的硬性诉求：
1. **显式、可读的状态流转**与**条件分支**（高风险 gate 要是确定性的，不能藏在 LLM 黑盒里）。
2. **可离线测试**：全链路（意图路由 / 子 Agent 派发 / 安全兜底 / 一般咨询）要能在无外部服务的 CI 里复现。
3. **可观测**：每个节点可写审计日志 / metric。
4. 与 **LangChain Function Calling / 工具生态**无缝衔接（子 Agent 以工具形式被调用）。

## 决策 (Decision)

采用 **LangGraph `StateGraph`** 实现主控状态机：

```
START ─▶ intent_router ─┬─▶ safety_fallback ─▶ END        (高风险)
                        │
                        └─▶ subagent_dispatcher ─▶ tool_executor ─▶ citation_validator ─▶ END
```

- **intent_router**：LLM Function Calling 输出 `intent / selected_subagent / is_high_risk`；前置**规则关键词层**对确定性短语短路，省 LLM 调用。
- 条件边：`is_high_risk` 为真 → `safety_fallback`；否则进子 Agent 派发链。
- **citation_validator**：校验输出引用可映射到知识库。
- 状态用 `TypedDict` + reducer 显式声明，节点只回写自己负责的字段。

理由：LangGraph 提供显式 state / 条件边 / 检查点，正好覆盖上述 1–4；节点是普通函数，天然可 monkeypatch 做离线确定性测试。

## 备选方案 (Alternatives)

- **裸 LangChain `AgentExecutor` / ReAct 循环**：控制流是黑盒，难以做**确定性**的高风险短路与分支级审计，也难离线复现完整路径。
- **Dify 全量编排**：可视化与上手快，但会把核心控制流锁进平台，版本化 / 单测 / 私有化部署偏弱。→ 折中：**仅在「健康数据洞察」子链**用 Dify 做可视化编排，主控仍用 LangGraph。
- **自研状态机**：要重复造 LangGraph 已提供的 state reducer / 条件边 / checkpoint 能力，性价比低。

## 影响 (Consequences)

**正面**
- 状态机显式可读，高风险 gate 等条件分支一目了然。
- 每个节点可 monkeypatch → happy-path 全链路测试纳入 CI（离线确定性）。
- 节点级 metric / 审计日志，SRE 看板可观测子 Agent 失败率。
- 新增子 Agent = 加一条边 + 一个 dispatcher 分支，扩展成本低。

**代价 / 风险**
- LangGraph 0.2 API 仍在演进：节点返回空 `{}` 会触发 `InvalidUpdateError`（W01 已遇到 3 处 noop-write 崩溃），约定**每个节点至少回写一个 schema 字段**。
- 需固定版本（pin），避免随上游收紧规则而无声破坏。
- 团队需理解 state / 边 / reducer 心智模型，有学习曲线。

**关联**
- W01 已落地并验证：图测试套件纳入 CI，修复 3 个 noop-write bug；详见 `tests/test_nutritionist_graph.py`、`WEEKLY_LOG.md`。
