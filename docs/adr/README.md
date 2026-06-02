# 架构决策记录 | Architecture Decision Records (ADR)

记录 NutriCore 的重大技术选型及其理由，方便后来者（含未来的自己）理解「**为什么是这样**」。

## 索引

| 编号 | 标题 | 状态 |
| ---- | ---- | ---- |
| [0001](0001-why-langgraph.md) | 用 LangGraph 编排 AI 营养师主控 | Accepted |

## 何时写 ADR

引入或替换框架 / 协议 / 存储 / 检索策略，或任何「**当时纠结过、半年后会忘记为什么**」的决策。
小改动不必写。

## 模板

```markdown
# ADR-NNNN: <决策标题>

- 状态：Proposed | Accepted | Superseded by ADR-XXXX
- 日期：YYYY-MM-DD

## 背景 (Context)
要解决什么问题、约束与诉求。

## 决策 (Decision)
选了什么、怎么做。

## 备选方案 (Alternatives)
还考虑过什么，为什么没选。

## 影响 (Consequences)
正面收益、代价 / 风险、后续关联。
```

文件名用 `NNNN-kebab-title.md`，编号递增。
