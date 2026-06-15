"""Eval 看板统一入口 —— 一次跑齐 Screening / Plan / Insight 三维并汇总。

    python -m app.evaluation.dashboard          # 离线：纯确定性 + 注入 stub
    python -m app.evaluation.dashboard --live    # 接真实栈：真实 recall@k + 端到端 SQL 生成

**离线**（默认）：无 LLM / DB / Milvus，跑得出 screening 全维、plan 的 compliance/citation、
insight 的 gate/chart/可读性；recall@k 与 e2e_sql_accuracy 记 0.0。

**live**（W09 兑现）：把 plan 的 `recall_at_k` 接真实 `retrieve_plan_evidence`（需 Milvus + 已灌 KB），
把 insight 的 `e2e_sql_accuracy` 接真实 `generate_sql`（需 LLM 后端可达：本地 Ollama / vLLM / DeepSeek 任一）。
某一真实依赖不可用 → 该维度回落离线值并在 stderr 标注，不让整块看板崩。
"""
from __future__ import annotations

from app.evaluation.insight_eval import GOLD_SQL_GEN_CASES, evaluate_insight
from app.evaluation.metrics import aggregate_dashboard
from app.evaluation.plan_eval import LIVE_RECALL_GOLD, evaluate_plan
from app.evaluation.screening_eval import evaluate_screening


def run_dashboard() -> dict:
    """离线汇总三维评测 → 看板统一结构 {MetricClassName: {field: value}}。"""
    return aggregate_dashboard(
        evaluate_screening(),
        evaluate_plan(),
        evaluate_insight(),
    )


def _live_recall_retriever():
    """真实方案检索 → 同步 retriever(query) -> ranked doc_ids（桥接 async）。"""
    import asyncio

    from app.agents.meal_plan.retriever import retrieve_plan_evidence

    def retriever(query: str) -> list[str]:
        ev = asyncio.run(retrieve_plan_evidence(query, top_k=20, rerank_top=8))
        return [e["doc_id"] for e in ev]

    return retriever


def _live_sql_generator():
    """真实 LLM 直出 SQL → 同步 generator(question, user_id) -> sql（桥接 async）。"""
    import asyncio

    from app.agents.data_insight.nl2sql import generate_sql

    return lambda question, user_id: asyncio.run(generate_sql(question, user_id))


def run_dashboard_live() -> dict:
    """接真实栈汇总。recall / e2e 各自独立兜底：真实依赖不可用（import 失败或运行时连不上）
    就回落该维度的离线评测，不让整块看板崩。"""
    import sys

    try:  # plan：真实 recall@k（需 Milvus + 已灌 KB）
        plan = evaluate_plan(recall_gold=LIVE_RECALL_GOLD, retriever=_live_recall_retriever())
    except Exception as e:
        print(f"[dashboard] recall@k 回落离线（真实检索不可用）：{e}", file=sys.stderr)
        plan = evaluate_plan()

    try:  # insight：真实端到端 SQL 生成（需 LLM 后端可达）
        insight = evaluate_insight(
            sql_gen_cases=GOLD_SQL_GEN_CASES, sql_generator=_live_sql_generator()
        )
    except Exception as e:
        print(f"[dashboard] e2e_sql 回落离线（真实生成不可用）：{e}", file=sys.stderr)
        insight = evaluate_insight()

    return aggregate_dashboard(evaluate_screening(), plan, insight)


def main() -> None:
    import json
    import sys

    live = "--live" in sys.argv[1:]
    board = run_dashboard_live() if live else run_dashboard()
    print(json.dumps(board, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
