"""评测看板指标定义。

筛查：评分准确率 / 报告完整度 / 复测一致性
方案：召回率 Top-K / 引用命中率 / 方案合规率
洞察：SQL 准确率 / 图表生成成功率 / 解读可读性
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ScreeningMetric:
    score_accuracy: float          # 与人工标注的一致率
    report_completeness: float     # 必填字段完整度
    retest_consistency: float      # 同用户短期复测一致率


@dataclass
class PlanMetric:
    recall_at_k: float             # 知识库召回 Top-K
    citation_hit_rate: float       # 方案中引用能映射到知识库的比例
    compliance_rate: float         # 通过双层校验的方案占比


@dataclass
class InsightMetric:
    sql_accuracy: float
    chart_success_rate: float
    interpretation_readability: float


def aggregate_dashboard(*metrics) -> dict:
    """汇总到看板的统一结构。"""
    out: dict = {}
    for m in metrics:
        out[type(m).__name__] = m.__dict__
    return out
