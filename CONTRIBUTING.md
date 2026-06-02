# 贡献指南 | Contributing

感谢参与 **NutriCore**。本文档是开发协作的基线约定（skeleton），随项目演进补充。

> 架构总览见 [`docs/architecture.md`](docs/architecture.md)；本地部署见 [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)；
> 重大技术选型记录在 [`docs/adr/`](docs/adr/)。

---

## 1. 开发环境

- **Python 3.11+**（CI 跑 3.11；`requires-python = ">=3.11"`）。
- 安装依赖：`pip install -r requirements.txt`。
- 配置 `.env`（参考 `.env.example`，至少需 `DEEPSEEK_API_KEY` 等）。**`.env` 已 gitignore，严禁提交。**
- 完整后端栈（MySQL / Redis / Milvus / MinIO / etcd）：`docker compose up -d`，详见 `docs/DEPLOYMENT.md`。
  - 纯逻辑开发与单测**无需**起全栈（见 §3）。

## 2. 代码规范

- **Ruff**（pin `ruff==0.15.15`，`line-length = 110`，`target-version = "py311"`）：
  ```bash
  ruff check app tests
  ruff check --fix app tests   # 自动修可修项
  ```
- 选用规则：`E F I B UP PL RUF`；有意忽略见 `pyproject.toml`（中文医学术语的 RUF001/2/3、FastAPI `Depends` 的 B008、有意 lazy import 的 PLC0415 等）。
- **依赖懂得懒加载**：重型依赖（paddle / numpy / sentence-transformers / fastapi+prometheus 等）放到**函数内** import，让纯逻辑模块能在轻量环境（CI pure-logic）被导入。

## 3. 测试

测试分两层，均可**离线**跑（用 monkeypatch 把 LLM / 检索 / DB 打成确定性）：

```bash
# 纯逻辑层（不依赖外部服务，CI 必跑）
pytest tests/test_nrs2002.py tests/test_meal_plan_validator.py tests/test_nl2sql_safety.py \
       tests/test_echarts.py tests/test_screening_eval.py tests/test_plan_eval.py \
       tests/test_insight_eval.py tests/test_dashboard.py -v

# 图 / 记忆层（monkeypatch 离线）
pytest tests/test_nutritionist_graph.py tests/test_short_term_memory.py -v
```

约定：
- **新增测试必须加进 `.github/workflows/ci.yml` 对应步骤** —— 不在 CI 里的测试 = 会腐烂的测试。
- 需重型栈（真实 paddle / Milvus / vLLM）的端到端测试，用 marker 默认 deselect，CI 只跑离线确定性部分。
- 评测看板：`python -m app.evaluation.dashboard` 跑确定性 gold 集，输出三维指标 JSON。

## 4. 提交规范

[Conventional Commits](https://www.conventionalcommits.org/)：

```
feat(meal_plan): 7 天方案生成主链
fix(safety): 多模态消息高风险 gate
test(evaluation): 筛查评测金标准
docs(adr): ADR-0001 why LangGraph
```

常用 type：`feat / fix / refactor / test / docs / chore / perf / ci / style`。

## 5. 分支与 PR

- **不直推 `main`**：从 `main` 切 feature 分支（`feat/xxx`、`fix/xxx`、`docs/xxx`）。
- 推分支 → `gh pr create` → CI 绿 → `gh pr merge --squash --delete-branch`。
- **每次推完看一眼 CI**（`gh pr checks` / `gh run watch`），不放任红灯。

## 6. 架构决策记录（ADR）

重大技术选型（框架 / 协议 / 存储 / 检索策略等）写一条 ADR 到 [`docs/adr/`](docs/adr/)，
格式见 [`docs/adr/README.md`](docs/adr/README.md)。已有：
- [ADR-0001 · 用 LangGraph 编排 AI 营养师主控](docs/adr/0001-why-langgraph.md)

## 7. 安全红线（务必遵守）

- **绝不提交** `.env` / 真实业务数据 / 密钥 / 模型权重。本仓库是离职后基于公开技术栈 mock 的版本。
- 临床 / 用药 / 急重症 / 孕产期问题必须路由到 **safety_fallback**（"建议就医"），不得由模型自由作答。
- `APP_ENV=prod` 下默认密钥须 fail-fast 拒绝启动。
