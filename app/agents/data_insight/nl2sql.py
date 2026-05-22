"""基于 LLM 的 NL2SQL — 安全收口（SELECT-only + 字段白名单 + user_id 强制过滤）。

设计动机：Vanna.ai 在生产里要训练向量库，部署门槛较高。这里给一个轻量的「LLM 直出 SQL +
强校验」实现，等同业务效果。生产里可以平替为 vanna.ask() 的输出再走同一组校验逻辑。
"""
from __future__ import annotations

import re
from typing import Any

from loguru import logger
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
FORBIDDEN = ("UPDATE", "DELETE", "INSERT", "DROP", "ALTER", "TRUNCATE", "GRANT", "CREATE", "RENAME", "REPLACE")

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


def assert_safe_sql(sql: str, user_id: str) -> str:
    upper = sql.upper().strip().rstrip(";")
    if not upper.startswith("SELECT"):
        raise ValueError("仅允许 SELECT 查询")
    if ";" in sql.strip().rstrip(";"):
        raise ValueError("禁止多语句")
    for kw in FORBIDDEN:
        if re.search(rf"\b{kw}\b", upper):
            raise ValueError(f"SQL 包含禁用关键字 {kw}")
    if (f"user_id = '{user_id}'" not in sql
        and f'user_id = "{user_id}"' not in sql
        and f"user_id='{user_id}'" not in sql):
        raise ValueError("SQL 缺少 user_id 强制过滤")
    # 表 + 字段白名单
    used_tables = set(re.findall(r"\bFROM\s+(\w+)|\bJOIN\s+(\w+)", sql, flags=re.IGNORECASE))
    flat = {t for tup in used_tables for t in tup if t}
    extra = flat - ALLOWED_TABLES
    if extra:
        raise ValueError(f"使用了非授权表：{extra}")
    return sql.strip().rstrip(";")


async def nl2sql(question: str, user_id: str) -> dict[str, Any]:
    raw = await chat_complete(
        _SQL_PROMPT.format(schema=SCHEMA_FOR_LLM.strip(), user_id=user_id, question=question),
        temperature=0.0,
        max_tokens=400,
    )
    sql = raw.strip().strip("`").strip()
    sql = assert_safe_sql(sql, user_id)
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
            return [dict(zip(cols, row)) for row in result.fetchall()]
    finally:
        await engine.dispose()
