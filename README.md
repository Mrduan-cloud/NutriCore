# NutriCore · AI 营养健康多智能体协同平台

> **NutriCore** is a multi-agent platform that delivers personalized nutrition companionship — covering nutrition risk screening, AI nutritionist consultation, personalized meal plans and health data insights.
>
> Built with **FastAPI · LangGraph · LangChain · Dify · Vanna.ai · vLLM · Milvus · MySQL · MinIO**.

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2+-orange.svg)](https://langchain-ai.github.io/langgraph/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

---

## 项目背景 | Background

优质营养师咨询费用高昂、预约周期长；通用建议无法匹配个人 **BMI / 慢病史 / 过敏源 / 饮食偏好** 差异；营养摄入与体征数据分散，难以形成长期洞察。

**NutriCore** 通过 4 个核心智能体，覆盖「营养风险筛查 → AI 营养师咨询 → 个性化营养方案 → 健康数据洞察」全链路，提供 7×24 小时个性化营养陪伴服务。

> Quality nutritionist consultations are expensive and hard to schedule. Generic advice fails to account for personal BMI, chronic disease history, allergies, and dietary preferences. NutriCore solves this with four collaborating agents that screen, consult, plan, and analyze — all backed by a private-deployed LLM stack.

---

## 核心能力 | Key Features

| 智能体 / Agent              | 能力 / Capability                                                                                      |
| --------------------------- | ------------------------------------------------------------------------------------------------------ |
| **AI 营养师 Agent**         | LangGraph 主控状态机 · ReAct 推理 · 多轮记忆 · 子 Agent 路由 · 高风险兜底                              |
| **营养风险筛查 Agent**      | NRS2002 评分算法 · 断点续答 · 异常实时拦截 · PDF 风险报告 · 评测看板                                   |
| **个性化营养方案 Agent**    | BM25 + BGE 混合检索 · RRF 融合 · Cross-Encoder 精排 · 7 天方案生成 · 引用强约束校验                    |
| **健康数据洞察 Agent**      | Vanna.ai NL2SQL · Dify 可视化编排 · ECharts 自动出图 · 三层数据隔离 · 四段式洞察报告                   |

---

## 系统架构 | Architecture

```
                ┌─────────────────────────────────────────────────────────┐
                │                  FastAPI Gateway (API)                  │
                └────────────────────────┬────────────────────────────────┘
                                         │
                ┌────────────────────────▼────────────────────────────────┐
                │             AI 营养师 Agent (LangGraph)                │
                │   意图识别 → 子 Agent 路由 → 工具调用 → 引用核验       │
                └──┬──────────────┬───────────────┬─────────────────┬─────┘
                   │              │               │                 │
            ┌──────▼─────┐ ┌──────▼─────┐ ┌──────▼──────┐  ┌───────▼────────┐
            │ 营养风险   │ │ 个性化营养 │ │ 健康数据    │  │ Function Calling│
            │ 筛查 Agent │ │ 方案 Agent │ │ 洞察 Agent  │  │ 工具集          │
            │ (NRS2002)  │ │ (RAG+PDF)  │ │ (NL2SQL)    │  │ BMI/能量/食谱.. │
            └──────┬─────┘ └──────┬─────┘ └──────┬──────┘  └────────────────┘
                   │              │              │
            ┌──────▼──────────────▼──────────────▼─────────────────────────┐
            │   Milvus (向量)  ·  MySQL (画像 / 业务)  ·  Redis (缓存)     │
            │   MinIO (PDF / 报告)  ·  vLLM (本地化大模型)                │
            └──────────────────────────────────────────────────────────────┘
```

详细架构图见 [`docs/architecture.md`](docs/architecture.md)。

---

## 技术栈 | Tech Stack

- **Agent 框架**：LangGraph (主控编排) · LangChain (工具封装与 ReAct) · Dify (数据洞察可视化编排)
- **大模型**：vLLM 私有化部署 · BGE Embedding · BGE Reranker (Cross-Encoder)
- **检索 / 知识库**：Milvus (向量) + BM25 关键词召回 + RRF 融合 + Cross-Encoder 精排
- **NL2SQL**：Vanna.ai
- **后端 / API**：FastAPI · Pydantic · Tortoise-ORM · 异步任务
- **数据 / 存储**：MySQL · Redis · MinIO
- **可视化**：ECharts (服务端渲染)
- **部署**：Docker · docker-compose · Nginx

---

## 目录结构 | Project Layout

```
NutriCore/
├── app/
│   ├── main.py                 # FastAPI 入口
│   ├── config.py               # 全局配置
│   ├── agents/
│   │   ├── nutritionist/       # AI 营养师主 Agent (LangGraph)
│   │   │   ├── graph.py        # 状态机定义
│   │   │   ├── nodes.py        # 节点实现 (意图识别 / 路由 / 兜底)
│   │   │   ├── memory.py       # 实体抽取 + 用户画像沉淀
│   │   │   └── prompts.py
│   │   ├── risk_screening/     # 营养风险筛查 (NRS2002)
│   │   │   ├── nrs2002.py
│   │   │   ├── report.py       # ReportLab PDF
│   │   │   └── schemas.py
│   │   ├── meal_plan/          # 个性化营养方案
│   │   │   ├── retriever.py    # 混合检索
│   │   │   ├── generator.py    # 7 天方案生成
│   │   │   ├── validator.py    # Pydantic + JSONSchema 双层校验
│   │   │   └── pdf_export.py
│   │   └── data_insight/       # 健康数据洞察
│   │       ├── nl2sql.py       # Vanna.ai
│   │       ├── dify_client.py  # Dify Workflow API
│   │       └── echarts.py
│   ├── tools/                  # Function Calling 工具集
│   │   ├── bmi.py
│   │   ├── energy.py
│   │   ├── recipe.py
│   │   ├── food_nutrition.py
│   │   └── disease_taboo.py
│   ├── rag/                    # 通用 RAG 组件
│   │   ├── ingestion.py        # 切分 + 元数据增强 + 向量化
│   │   ├── hybrid_retrieval.py # BM25 + BGE + RRF
│   │   └── reranker.py         # Cross-Encoder
│   ├── api/                    # FastAPI 路由
│   ├── core/                   # LLM / Embedding / DB / Storage
│   ├── schemas/                # 全局 Pydantic 模型
│   └── evaluation/             # 评测指标看板
├── docs/                       # 架构文档与图
├── scripts/                    # 一键启动 / 数据初始化
├── tests/
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

---

## 快速开始 | Quick Start

> 完整的「个人电脑 / 企业私有化服务器」部署文档见 **[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)**。
> 下面是 5 行命令快起版本。

```bash
git clone https://github.com/Mrduan-cloud/NutriCore.git && cd NutriCore
cp .env.example .env                                    # 编辑 JWT_SECRET_KEY / LLM_BASE_URL 等
docker compose up -d                                    # 拉起 MySQL/Redis/Milvus/MinIO/API
docker compose exec api python -m scripts.seed         # 初始化数据库 + 知识库 + Demo 数据
docker compose exec api python -m scripts.demo         # 跑端到端 demo
```

打开：

- Swagger 文档: <http://localhost:8000/docs>
- 健康探测: <http://localhost:8000/ready>
- MinIO 控制台: <http://localhost:9001>
- Prometheus 指标: <http://localhost:8000/metrics>

### 推荐配置 / Hardware

| 场景             | CPU      | 内存       | 磁盘            | GPU                                   | 模型                                     |
| ---------------- | -------- | ---------- | --------------- | ------------------------------------- | ---------------------------------------- |
| 个人电脑开发     | 8 核+    | 32 GB      | 100 GB+ SSD     | 可选（远程 LLM 即可）                 | Ollama qwen2.5:7b-instruct（替代方案）   |
| **小公司生产 ⭐**| 16 核    | 64 GB      | 500 GB+ SSD     | **2× RTX 4090 24G**                   | **vLLM + Qwen2.5-32B-Instruct-AWQ + TP=2** |
| 中型企业生产     | 16 核    | 128 GB     | 1 TB+ SSD       | 2× L40S 48G / 2× A100 80G             | 32B FP16 / 70B AWQ                       |

> 默认配置面向**小公司私有化**场景：2× RTX 4090（约 5–7 万整机）+ AWQ Int4 量化让 32B 显存压到 ~20 GB，单一客户私有化交付即可回本。
> 硬件成本对照、ROI 测算、按公司阶段选配指南：[`docs/HARDWARE.md`](docs/HARDWARE.md)
> 完整操作系统选型 / 内核调参 / HTTPS / 信创 / 备份监控：[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)

---

## 关键设计要点 | Design Highlights

### 1. LangGraph 主控状态机

```
意图识别 → 子 Agent 路由 → 工具调用 → 引用核验 → 安全兜底
```

3 个子 Agent（筛查 / 方案 / 洞察）以 `StructuredTool` 形式封装为可调用工具，由主 Agent 基于 **ReAct** 模式循环调用并聚合上下文；**高风险问题**（用药 / 急重症 / 孕产期）自动触发「建议就医」兜底话术。

### 2. 多轮记忆 & 用户画像

通过实体抽取沉淀：`weight · BMI · 慢病史 · 过敏源 · 饮食偏好 · 预算` 等画像字段，跨会话保持个性化一致性。

### 3. 混合检索 + 精排

`BM25 + BGE 向量` 多路召回 → `RRF` 融合 → `Cross-Encoder` 精排。Top-20 召回率从 ~75% 提升至 **90%+**。

### 4. 引用强约束

方案 JSON 走 **Pydantic + JSONSchema 双层校验**（热量区间 / 营养素配比 / 忌口冲突），每条建议强制携带知识库片段引用，从模型侧消除「无依据胡编」风险。

### 5. 数据隔离（Data Insight Agent）

`user_id 强制过滤 + 字段白名单 + SELECT-only` 三层防护，确保用户仅能查询自身数据。

---

## 评测指标 | Evaluation

| 模块             | 指标                                   |
| ---------------- | -------------------------------------- |
| 营养风险筛查     | 评分准确率 · 报告完整度 · 复测一致性   |
| 个性化营养方案   | 召回率（Top-K）· 引用命中率 · 方案合规率 |
| 健康数据洞察     | SQL 准确率 · 图表生成成功率 · 解读可读性 |

---

## API 一览 | API Overview

| 路径                              | 方法 | 说明                          |
| --------------------------------- | ---- | ----------------------------- |
| `/api/chat/nutritionist`          | POST | 与 AI 营养师对话              |
| `/api/screening/nrs2002`          | POST | 提交 NRS2002 筛查问卷         |
| `/api/screening/{id}/report`      | GET  | 下载筛查 PDF 报告             |
| `/api/plan/generate`              | POST | 生成 7 天个性化营养方案       |
| `/api/insight/query`              | POST | 自然语言查询健康数据并出图    |
| `/api/profile/{user_id}`          | GET  | 查询用户画像                  |

完整 schema 见 `/docs` (Swagger UI)。

---

## License

[MIT](LICENSE) © 2025-2026 Mrduan-cloud
