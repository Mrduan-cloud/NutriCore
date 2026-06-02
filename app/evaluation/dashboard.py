"""Eval 看板统一入口 —— 一次跑齐 Screening / Plan / Insight 三维并汇总。

    python -m app.evaluation.dashboard

打印完整看板 JSON。离线（无 LLM / DB / Milvus）跑确定性 + 注入式部分；
真实 recall@k / 端到端 SQL 生成准确率留 W09 接真实栈。
"""
from __future__ import annotations

from app.evaluation.insight_eval import evaluate_insight
from app.evaluation.metrics import aggregate_dashboard
from app.evaluation.plan_eval import evaluate_plan
from app.evaluation.screening_eval import evaluate_screening


def run_dashboard() -> dict:
    """汇总三维评测 → 看板统一结构 {MetricClassName: {field: value}}。"""
    return aggregate_dashboard(
        evaluate_screening(),
        evaluate_plan(),
        evaluate_insight(),
    )


def main() -> None:
    import json

    print(json.dumps(run_dashboard(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
