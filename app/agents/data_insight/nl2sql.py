"""基于 LLM 的 NL2SQL — 安全收口（SELECT-only + 字段白名单 + user_id 强制过滤）。

设计动机：Vanna.ai 在生产里要训练向量库，部署门槛较高。这里给一个轻量的「LLM 直出 SQL +
强校验」实现，等同业务效果。生产里可以平替为 vanna.ask() 的输出再走同一组校验逻辑。
"""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings
from app.core.llm import chat_complete

# 允许暴露给 LLM 的 schema 摘要 — 注意 user_id 字段必须存在
SCHEMA_FOR_LLM = """
表 daily_intake (user_id, date, kcal, protein, carb, fat, water_ml)
表 vitals (user_id, date, weight_kg, steps, sleep_hours)
所有查询必须包含 user_id = '<用户>' 的过滤条件。
"""

ALLOWED_TABLES = {"daily_intake", "vitals"}
ALLOWED_FIELDS = {
    "daily_intake": {"user_id", "date", "kcal", "protein", "carb", "fat", "water_ml"},
    "vitals": {"user_id", "date", "weight_kg", "steps", "sleep_hours"},
}
# 禁用关键字。除常规写库 / DDL 外,还显式封掉几个「能绕过单用户隔离」的口子:
#   UNION  —— `... UNION SELECT ... WHERE user_id='他人'`,只要第一段带本人 id 就能拼出越权读
#   INTO   —— `SELECT ... INTO OUTFILE/DUMPFILE` 落盘外泄
#   OR/XOR —— 单用户分析查询从不需要 OR;放开就会被 `... user_id='我' OR 1=1` 整段绕过强制过滤
#   INFORMATION_SCHEMA —— 元数据库枚举(表白名单也会拦,这里显式兜底)
FORBIDDEN = (
    "UPDATE", "DELETE", "INSERT", "DROP", "ALTER", "TRUNCATE", "GRANT",
    "CREATE", "RENAME", "REPLACE",
    "UNION", "INTO", "INFORMATION_SCHEMA", "OR", "XOR",
)

# 字段白名单依赖一个「合法非标识符词表」:凡不是关键字 / 函数 / 授权表 / 授权字段 / 别名的
# 裸标识符,一律判为越权字段并拒绝(fail-closed)。函数调用还要额外落在 _ALLOWED_FUNCS 内,
# 顺手封掉 SLEEP / BENCHMARK / LOAD_FILE / UPDATEXML 这类注入常用函数。
_ALLOWED_KEYWORDS = {
    "SELECT", "DISTINCT", "FROM", "AS", "WHERE", "AND", "NOT", "NULL", "IS",
    "IN", "LIKE", "BETWEEN", "ON", "JOIN", "INNER", "LEFT", "RIGHT", "OUTER",
    "CROSS", "USING", "GROUP", "BY", "ORDER", "ASC", "DESC", "HAVING",
    "LIMIT", "OFFSET", "CASE", "WHEN", "THEN", "ELSE", "END", "INTERVAL",
    "TRUE", "FALSE", "DIV", "MOD",
}
_ALLOWED_FUNCS = {
    "COUNT", "SUM", "AVG", "MIN", "MAX", "ROUND", "ABS", "CEIL", "CEILING",
    "FLOOR", "COALESCE", "IFNULL", "NULLIF", "IF", "CAST", "GREATEST", "LEAST",
    "DATE", "NOW", "CURDATE", "CURRENT_DATE", "DATE_FORMAT", "DATE_SUB",
    "DATE_ADD", "DATEDIFF", "TIMESTAMPDIFF", "EXTRACT",
    "YEAR", "MONTH", "DAY", "WEEK", "HOUR", "MINUTE", "SECOND",
    "DAYOFWEEK", "DAYNAME", "MONTHNAME", "WEEKDAY",
}
_KW_L = {k.lower() for k in _ALLOWED_KEYWORDS}
_FN_L = {f.lower() for f in _ALLOWED_FUNCS}
_VOCAB_L = _KW_L | _FN_L
# FROM/JOIN 后面紧跟的若是这些词,说明没有表别名,别误收成别名
_ALIAS_STOP = {"ON", "WHERE", "GROUP", "ORDER", "INNER", "LEFT", "RIGHT",
               "OUTER", "CROSS", "JOIN", "USING", "LIMIT", "HAVING", "AS"}
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_STRING_LITERAL = re.compile(r"'(?:[^'\\]|\\.|'')*'|\"(?:[^\"\\]|\\.|\"\")*\"")

_SQL_PROMPT = """你是 SQL 生成器。基于以下 schema：

{schema}

把用户的自然语言查询翻译成单条 MySQL SELECT 查询。要求：
1. 仅使用 SELECT，禁止其它语句
2. 必须包含 user_id = '{user_id}'
3. 仅使用 schema 中列出的字段
4. 必要时按时间倒序 + LIMIT 收口

只输出 SQL，单条语句，不要带反引号或解释。

用户问题：{question}
"""


def _strip_string_literals(sql: str) -> str:
    """把 '...' / "..." 字面量替换成空格 —— 之后的结构 / 标识符校验都在「去字面量」副本上做,
    避免字面量内容(如备注里写了 DELETE、或值里带 -- )污染关键字 / 注释 / 字段判定。"""
    return _STRING_LITERAL.sub(" ", sql)


def _table_refs(stripped: str) -> tuple[set[str], set[str]]:
    """从去字面量的 SQL 里提取 (真实表名集合, 表别名集合)。"""
    tables: set[str] = set()
    aliases: set[str] = set()
    for m in re.finditer(
        r"\b(?:FROM|JOIN)\s+([A-Za-z_]\w*)(?:\s+(?:AS\s+)?([A-Za-z_]\w*))?",
        stripped, flags=re.IGNORECASE,
    ):
        tables.add(m.group(1).lower())
        alias = m.group(2)
        if alias and alias.upper() not in _ALIAS_STOP:
            aliases.add(alias.lower())
    return tables, aliases


def _assert_fields_whitelisted(stripped: str, tables: set[str], table_aliases: set[str]) -> None:
    """字段白名单(Layer 2):任何裸标识符都必须是 关键字/函数/授权表/表别名/授权字段/AS 别名 之一。"""
    allowed_fields: set[str] = set()
    for t in tables:
        allowed_fields |= {f.lower() for f in ALLOWED_FIELDS.get(t, set())}

    # 裸 * 会绕过字段白名单(投影出全部列);仅放行紧跟 '(' 的 COUNT(*)/SUM(*) 形态
    for m in re.finditer(r"\*", stripped):
        if not stripped[: m.start()].rstrip().endswith("("):
            raise ValueError("禁止 SELECT * / 表.*,必须显式列出白名单字段")

    as_aliases = {a.lower() for a in re.findall(r"\bAS\s+([A-Za-z_]\w*)", stripped, re.IGNORECASE)}
    safe = _VOCAB_L | {t.lower() for t in tables} | table_aliases | allowed_fields | as_aliases

    for m in _IDENT.finditer(stripped):
        low = m.group(0).lower()
        is_call = low not in _KW_L and stripped[m.end():].lstrip().startswith("(")
        if is_call:
            if low not in _FN_L:
                raise ValueError(f"使用了未授权函数：{m.group(0)}")
            continue
        if low not in safe:
            raise ValueError(f"使用了未授权字段/标识符：{m.group(0)}")


def assert_safe_sql(sql: str, user_id: str) -> str:
    """三层隔离收口:① SELECT-only 单语句 ② 表 + 字段白名单 ③ user_id 强制过滤。

    刻意收得很紧(禁 OR / 子查询 / UNION / 注释):单用户分析查询本就不需要它们,
    放开任何一个都会成为越权读他人数据或绕过强制过滤的口子。任一校验不过即抛 ValueError。
    """
    raw = sql.strip().rstrip(";")
    stripped = _strip_string_literals(raw)
    upper = stripped.upper()

    # ── Layer 1:SELECT-only,单条、无子查询、无注释、无禁用关键字 ──
    if not upper.lstrip().startswith("SELECT"):
        raise ValueError("仅允许 SELECT 查询")
    if ";" in raw:
        raise ValueError("禁止多语句")
    if len(re.findall(r"\bSELECT\b", upper)) != 1:
        raise ValueError("禁止子查询 / 多个 SELECT")
    if re.search(r"--|#|/\*|\*/", stripped):
        raise ValueError("禁止 SQL 注释")
    for kw in FORBIDDEN:
        if re.search(rf"\b{kw}\b", upper):
            raise ValueError(f"SQL 包含禁用关键字 {kw}")

    # ── Layer 3:user_id 强制过滤(必须是当前登录用户本人的 id,允许空白/引号变体) ──
    uid = re.escape(user_id)
    if not re.search(rf"\buser_id\s*=\s*(['\"]){uid}\1", sql):
        raise ValueError("SQL 缺少 user_id 强制过滤(或过滤的不是当前用户)")

    # ── Layer 2:表白名单 + 字段白名单 ──
    tables, table_aliases = _table_refs(stripped)
    extra = tables - ALLOWED_TABLES
    if extra:
        raise ValueError(f"使用了非授权表：{extra}")
    _assert_fields_whitelisted(stripped, tables, table_aliases)

    return raw


async def generate_sql(question: str, user_id: str) -> str:
    """仅做「LLM 直出 SQL」这一步 —— 不过 gate、不连库。

    抽成独立入口是为了让端到端 NL2SQL 评测（`app.evaluation.insight_eval`）能注入它跑真实
    生成、只校验「生成对不对」，而不必拉起 MySQL 执行。`nl2sql` 在其之上叠 gate + 执行。
    """
    raw = await chat_complete(
        _SQL_PROMPT.format(schema=SCHEMA_FOR_LLM.strip(), user_id=user_id, question=question),
        temperature=0.0,
        max_tokens=400,
    )
    return raw.strip().strip("`").strip()


async def nl2sql(question: str, user_id: str) -> dict[str, Any]:
    sql = assert_safe_sql(await generate_sql(question, user_id), user_id)
    rows = await _run_select(sql)
    return {"sql": sql, "rows": rows}


async def _run_select(sql: str) -> list[dict]:
    s = get_settings()
    dsn = (
        f"mysql+aiomysql://{s.mysql_user}:{s.mysql_password}"
        f"@{s.mysql_host}:{s.mysql_port}/{s.mysql_db}?charset=utf8mb4"
    )
    engine = create_async_engine(dsn, pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text(sql))
            cols = list(result.keys())
            return [dict(zip(cols, row, strict=True)) for row in result.fetchall()]
    finally:
        await engine.dispose()
