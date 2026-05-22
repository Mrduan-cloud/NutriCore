"""NL2SQL 安全收口测试 — 不需任何外部服务。"""
import pytest

from app.agents.data_insight.nl2sql import assert_safe_sql


def test_select_only():
    sql = "SELECT date, weight_kg FROM vitals WHERE user_id = 'u1' ORDER BY date DESC"
    assert assert_safe_sql(sql, "u1") == sql.strip().rstrip(";")


def test_reject_update():
    with pytest.raises(ValueError):
        assert_safe_sql("UPDATE vitals SET weight_kg=0 WHERE user_id='u1'", "u1")


def test_reject_multi():
    with pytest.raises(ValueError):
        assert_safe_sql("SELECT 1 FROM vitals WHERE user_id='u1'; DROP TABLE vitals;", "u1")


def test_require_user_id():
    with pytest.raises(ValueError):
        assert_safe_sql("SELECT date FROM vitals", "u1")


def test_reject_unknown_table():
    with pytest.raises(ValueError):
        assert_safe_sql("SELECT * FROM admin_secrets WHERE user_id='u1'", "u1")
