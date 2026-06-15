"""洞察 Agent 评测器 —— Insight 维度跑分。

四项指标分两类：

**离线确定性面（无 LLM / DB / Milvus，纳入 CI）**
- **sql_accuracy**：NL2SQL 安全收口 `assert_safe_sql` 的判定准确率（安全 SQL 放行 + 危险 SQL 拦截）。
  这是不依赖 LLM 即可评的「SQL 层」正确性，直接背书「三层数据隔离」声明。
- **chart_success_rate**：`rows_to_chart` 能产出可渲染图表（非 noData、有 series + type）的比例。
- **interpretation_readability**：洞察文本的确定性可读性启发式（分段 / 含数字 / 有建议 / 长度合理）。

**端到端面（需真实 / 注入 generator）**
- **e2e_sql_accuracy**（W09 新增）：LLM **直出** SQL 是否「安全（过 gate）∧ 语义正确（命中期望表/列）」。
  做成**注入式纯函数**：传入 `generator(question, user_id) -> sql` 回调即可——CI 用确定性 stub 验证
  打分逻辑（命中给分、跑偏扣分），live 用真实 `generate_sql`（接本地 Ollama / vLLM / DeepSeek）拿真数字。
  语义校验**不连库**：gate 已保证只含白名单标识符，故「期望表/列 ⊆ SQL 标识符」即为可靠的「答对了问题」代理。

只 import `assert_safe_sql` / `rows_to_chart`（均已被现有 CI 测试导入）+ metrics，保持 CI-light；
真实 generator 由调用方注入，本模块不 import `chat_complete`。
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from app.agents.data_insight.echarts import rows_to_chart
from app.agents.data_insight.nl2sql import assert_safe_sql
from app.evaluation.metrics import InsightMetric

_ADVICE_KEYWORDS = ("建议", "推荐", "注意", "可以")
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


@dataclass(frozen=True)
class SqlCase:
    sql: str
    user_id: str
    expected_safe: bool


@dataclass(frozen=True)
class ChartCase:
    rows: list[dict]
    question: str


def _is_safe(sql: str, user_id: str) -> bool:
    try:
        assert_safe_sql(sql, user_id)
    except ValueError:
        return False
    return True


def sql_accuracy(cases: list[SqlCase]) -> float:
    """安全收口判定准确率：gate 的放行 / 拦截与标注一致的比例。"""
    if not cases:
        return 0.0
    correct = sum(_is_safe(c.sql, c.user_id) == c.expected_safe for c in cases)
    return correct / len(cases)


# —— 端到端 NL2SQL 生成评测（注入式，需真实 / stub generator）——
SqlGenerator = Callable[[str, str], str]  # (question, user_id) -> 原始 SQL


@dataclass(frozen=True)
class SqlGenCase:
    """一条端到端 NL2SQL 用例：自然语言问题 + 期望命中的表/列。

    `ideal_sql` 仅供 CI stub generator 回放，**不参与打分**（打分只看注入 generator 的实际产出）。
    """

    question: str
    user_id: str
    expected_tables: frozenset[str]
    expected_fields: frozenset[str]
    ideal_sql: str = ""


def _identifiers(sql: str) -> set[str]:
    """SQL 里出现的全部标识符（小写）。gate 已过 → 只含白名单词，故可直接做期望表/列的包含判定。"""
    return {m.group(0).lower() for m in _IDENT.finditer(sql)}


def end_to_end_sql_accuracy(cases: list[SqlGenCase], generator: SqlGenerator) -> float:
    """端到端准确率：generator 直出的 SQL 同时满足「过安全 gate」∧「命中期望表/列」的比例。

    任一不满足即记 0：gate 不过（不安全 / 越权）算错；安全但答错了表或漏了关键字段也算错。
    不连库——语义正确性用「期望表/列 ⊆ SQL 标识符」近似（gate 已剔除非白名单标识符）。
    """
    if not cases:
        return 0.0
    ok = 0
    for c in cases:
        try:
            safe_sql = assert_safe_sql(generator(c.question, c.user_id), c.user_id)
        except Exception:
            continue  # 生成的 SQL 不安全 / 不合法 → 端到端失败
        idents = _identifiers(safe_sql)
        if c.expected_tables <= idents and c.expected_fields <= idents:
            ok += 1
    return ok / len(cases)


def replay_generator(cases: list[SqlGenCase]) -> SqlGenerator:
    """把一组用例的 `ideal_sql` 包成确定性 generator —— 供 CI 离线验证打分逻辑（不调 LLM）。"""
    table = {c.question: c.ideal_sql for c in cases}
    return lambda question, _user_id: table.get(question, "")


def _chart_ok(chart: dict) -> bool:
    if chart.get("noData"):
        return False
    series = chart.get("series") or []
    return bool(series) and bool(series[0].get("type"))


def chart_success_rate(cases: list[ChartCase]) -> float:
    if not cases:
        return 0.0
    ok = sum(_chart_ok(rows_to_chart(c.rows, c.question)) for c in cases)
    return ok / len(cases)


def readability_score(text: str) -> float:
    """洞察文本可读性启发式 ∈ [0,1]：长度合理 / 分段 / 含数字 / 有建议。"""
    text = (text or "").strip()
    if not text:
        return 0.0
    checks = (
        len(text) >= 40,                                  # 不过短
        len(text) <= 1200,                                # 不过长（4 段式洞察上限）
        text.count("\n") >= 2,                            # 多段结构
        bool(re.search(r"\d", text)),                     # 数据落地（含数字）
        any(k in text for k in _ADVICE_KEYWORDS),         # 有可执行建议
    )
    return sum(checks) / len(checks)


def interpretation_readability(texts: list[str]) -> float:
    if not texts:
        return 0.0
    return sum(readability_score(t) for t in texts) / len(texts)


# —— 内置 gold 集 ——
GOLD_SQL_CASES: list[SqlCase] = [
    SqlCase("SELECT date, weight_kg FROM vitals WHERE user_id = 'u1' ORDER BY date DESC", "u1", True),
    SqlCase("SELECT date, protein FROM daily_intake WHERE user_id = 'u1' LIMIT 30", "u1", True),
    SqlCase("UPDATE vitals SET weight_kg=0 WHERE user_id='u1'", "u1", False),          # 非 SELECT
    SqlCase("SELECT 1 FROM vitals WHERE user_id='u1'; DROP TABLE vitals;", "u1", False),  # 多语句
    SqlCase("SELECT date FROM vitals", "u1", False),                                   # 缺 user_id
    SqlCase("SELECT * FROM admin_secrets WHERE user_id='u1'", "u1", False),            # 非授权表
    SqlCase("DELETE FROM daily_intake WHERE user_id='u1'", "u1", False),               # 禁用词
    SqlCase("SELECT * FROM vitals JOIN users u ON u.id=vitals.user_id WHERE user_id='u1'", "u1", False),  # JOIN 非授权表
]

GOLD_CHART_CASES: list[ChartCase] = [
    ChartCase([{"date": "2026-05-01", "protein": 80}, {"date": "2026-05-02", "protein": 82}], "近30天蛋白质趋势"),
    ChartCase([{"meal": "早餐", "kcal": 500}, {"meal": "午餐", "kcal": 700}], "每餐热量"),
    ChartCase([{"碳水": 260, "蛋白质": 80, "脂肪": 65}], "三大产能营养素占比"),
]

# 代表性洞察文本（4 段式：概览 / 达标 / 异常 / 建议），供可读性评分演示。
GOLD_INSIGHT_TEXTS: list[str] = [
    "本次数据共 30 条。\n近 30 天日均蛋白质 78g，接近推荐的 80g。\n"
    "有 6 天低于 60g，集中在周末。\n建议周末增加一份鸡蛋或鱼类，把蛋白质补到 80g 以上。",
    "近 7 天日均饮水 1850ml，低于 2000ml 推荐线。\n"
    "周三、周四明显偏低（<1500ml）。\n建议在工位放置水杯定时提醒，注意餐前补水。",
]

# 端到端 NL2SQL gold：真实用户问法 → 期望命中的表/列。`ideal_sql` 供 CI stub 回放。
# schema：daily_intake(user_id,date,kcal,protein,carb,fat,water_ml) · vitals(user_id,date,weight_kg,steps,sleep_hours)
GOLD_SQL_GEN_CASES: list[SqlGenCase] = [
    SqlGenCase(
        "最近30天我每天摄入多少蛋白质", "u1",
        frozenset({"daily_intake"}), frozenset({"protein", "date"}),
        "SELECT date, protein FROM daily_intake WHERE user_id = 'u1' ORDER BY date DESC LIMIT 30",
    ),
    SqlGenCase(
        "我最近的体重变化趋势", "u1",
        frozenset({"vitals"}), frozenset({"weight_kg", "date"}),
        "SELECT date, weight_kg FROM vitals WHERE user_id = 'u1' ORDER BY date DESC LIMIT 30",
    ),
    SqlGenCase(
        "最近一周我平均每天喝多少水", "u1",
        frozenset({"daily_intake"}), frozenset({"water_ml"}),
        "SELECT AVG(water_ml) FROM daily_intake WHERE user_id = 'u1' ORDER BY date DESC LIMIT 7",
    ),
    SqlGenCase(
        "最近30天每日步数", "u1",
        frozenset({"vitals"}), frozenset({"steps", "date"}),
        "SELECT date, steps FROM vitals WHERE user_id = 'u1' ORDER BY date DESC LIMIT 30",
    ),
]


def evaluate_insight(
    sql_cases: list[SqlCase] | None = None,
    chart_cases: list[ChartCase] | None = None,
    insight_texts: list[str] | None = None,
    sql_gen_cases: list[SqlGenCase] | None = None,
    sql_generator: SqlGenerator | None = None,
) -> InsightMetric:
    """组装 InsightMetric。

    前三项永远离线确定性计算。`e2e_sql_accuracy` **仅在注入了 `sql_generator` 时**计算
    （需真实 / stub 生成），否则记 0.0（离线 CI 路径不评端到端，留给 live / 注入测试）。
    """
    e2e = (
        end_to_end_sql_accuracy(
            sql_gen_cases if sql_gen_cases is not None else GOLD_SQL_GEN_CASES,
            sql_generator,
        )
        if sql_generator is not None
        else 0.0
    )
    return InsightMetric(
        sql_accuracy=sql_accuracy(sql_cases if sql_cases is not None else GOLD_SQL_CASES),
        chart_success_rate=chart_success_rate(
            chart_cases if chart_cases is not None else GOLD_CHART_CASES
        ),
        interpretation_readability=interpretation_readability(
            insight_texts if insight_texts is not None else GOLD_INSIGHT_TEXTS
        ),
        e2e_sql_accuracy=e2e,
    )


def main() -> None:
    import json

    from app.evaluation.metrics import aggregate_dashboard

    print(json.dumps(aggregate_dashboard(evaluate_insight()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
