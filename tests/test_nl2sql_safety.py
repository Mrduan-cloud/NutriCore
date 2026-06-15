"""NL2SQL 三层隔离审计 —— 纯逻辑,不依赖任何外部服务(进 CI allowlist)。

data_insight 让 LLM 直出 SQL,唯一的安全边界就是 `assert_safe_sql`。这里按三层逐层钉死:
  Layer 1  SELECT-only:单条 SELECT,无子查询 / UNION / 注释 / 写库 / DDL / 危险函数
  Layer 2  表 + 字段白名单:只能碰授权表的授权列,禁 `SELECT *`
  Layer 3  user_id 强制过滤:必须按「当前登录用户本人」的 id 过滤,且不能被 OR 绕过

每条用例对应一个曾经可绕过的真实越权 / 注入向量,任一回归都会变红。
"""
import pytest

from app.agents.data_insight.nl2sql import _unwrap_sql, assert_safe_sql

# ─────────────────────────── Layer 1:SELECT-only ───────────────────────────


def test_select_only_passes():
    sql = "SELECT date, weight_kg FROM vitals WHERE user_id = 'u1' ORDER BY date DESC"
    assert assert_safe_sql(sql, "u1") == sql.strip().rstrip(";")


@pytest.mark.parametrize("sql", [
    "UPDATE vitals SET weight_kg=0 WHERE user_id='u1'",
    "DELETE FROM vitals WHERE user_id='u1'",
    "INSERT INTO vitals VALUES (1)",
    "DROP TABLE vitals",
    "ALTER TABLE vitals ADD c INT",
])
def test_reject_non_select_statements(sql):
    with pytest.raises(ValueError):
        assert_safe_sql(sql, "u1")


def test_reject_multi_statement():
    with pytest.raises(ValueError):
        assert_safe_sql("SELECT 1 FROM vitals WHERE user_id='u1'; DROP TABLE vitals;", "u1")


def test_reject_union_cross_user_leak():
    # 经典越权:第一段带本人 id 过校验,UNION 第二段读他人数据
    sql = ("SELECT kcal FROM daily_intake WHERE user_id='u1' "
           "UNION SELECT kcal FROM daily_intake WHERE user_id='victim'")
    with pytest.raises(ValueError):
        assert_safe_sql(sql, "u1")


def test_reject_subquery():
    sql = ("SELECT kcal FROM daily_intake WHERE user_id='u1' "
           "AND kcal IN (SELECT kcal FROM daily_intake)")
    with pytest.raises(ValueError):
        assert_safe_sql(sql, "u1")


@pytest.mark.parametrize("sql", [
    "SELECT date FROM vitals WHERE user_id='u1' -- AND extra",
    "SELECT date FROM vitals WHERE user_id='u1' # note",
    "SELECT date FROM vitals WHERE user_id='u1' /* hidden */",
])
def test_reject_comments(sql):
    with pytest.raises(ValueError):
        assert_safe_sql(sql, "u1")


def test_reject_into_outfile():
    sql = "SELECT date FROM vitals WHERE user_id='u1' INTO OUTFILE '/tmp/x'"
    with pytest.raises(ValueError):
        assert_safe_sql(sql, "u1")


@pytest.mark.parametrize("sql", [
    "SELECT SLEEP(5) FROM vitals WHERE user_id='u1'",
    "SELECT LOAD_FILE('/etc/passwd') FROM vitals WHERE user_id='u1'",
    "SELECT BENCHMARK(1000000, MD5('x')) FROM vitals WHERE user_id='u1'",
])
def test_reject_dangerous_functions(sql):
    with pytest.raises(ValueError):
        assert_safe_sql(sql, "u1")


# ───────────────────── Layer 2:表 + 字段白名单 ─────────────────────


def test_reject_unknown_table():
    with pytest.raises(ValueError):
        assert_safe_sql("SELECT secret FROM admin_secrets WHERE user_id='u1'", "u1")


def test_reject_join_unknown_table():
    sql = ("SELECT v.weight_kg FROM vitals v JOIN users u ON v.user_id=u.id "
           "WHERE v.user_id='u1'")
    with pytest.raises(ValueError):
        assert_safe_sql(sql, "u1")


@pytest.mark.parametrize("sql", [
    "SELECT * FROM vitals WHERE user_id='u1'",
    "SELECT vitals.* FROM vitals WHERE user_id='u1'",
])
def test_reject_star_projection(sql):
    with pytest.raises(ValueError):
        assert_safe_sql(sql, "u1")


def test_reject_unknown_field():
    # password 不在 vitals 白名单内 → 即便表合法也必须拒
    with pytest.raises(ValueError):
        assert_safe_sql("SELECT password FROM vitals WHERE user_id='u1'", "u1")


def test_accept_qualified_allowed_field():
    sql = "SELECT vitals.weight_kg FROM vitals WHERE vitals.user_id = 'u1'"
    assert assert_safe_sql(sql, "u1") == sql


def test_accept_aggregate_alias_and_date_math():
    # 真实分析查询不能被误杀:聚合 + 别名 + 日期函数 + INTERVAL 都应放行
    sql = ("SELECT AVG(kcal) AS avg_kcal FROM daily_intake "
           "WHERE user_id = 'u1' AND date >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)")
    assert assert_safe_sql(sql, "u1") == sql


def test_accept_count_star():
    sql = "SELECT COUNT(*) FROM daily_intake WHERE user_id = 'u1'"
    assert assert_safe_sql(sql, "u1") == sql


# ─────────────────── Layer 3:user_id 强制过滤 ───────────────────


def test_require_user_id_filter():
    with pytest.raises(ValueError):
        assert_safe_sql("SELECT date FROM vitals", "u1")


def test_reject_filtering_other_user():
    # 过滤的是别人的 id,不是当前登录用户 → 拒(隔离的核心)
    with pytest.raises(ValueError):
        assert_safe_sql("SELECT date FROM vitals WHERE user_id='victim'", "u1")


def test_reject_or_filter_bypass():
    # `... OR 1=1` 整段抹掉强制过滤 —— 必须挡住
    with pytest.raises(ValueError):
        assert_safe_sql("SELECT date FROM vitals WHERE user_id='u1' OR 1=1", "u1")


@pytest.mark.parametrize("sql", [
    "SELECT date FROM vitals WHERE user_id  =  'u1'",   # 多空格
    'SELECT date FROM vitals WHERE user_id = "u1"',      # 双引号
    "SELECT date FROM vitals WHERE user_id='u1'",         # 无空格
])
def test_accept_user_id_spacing_and_quote_variants(sql):
    assert assert_safe_sql(sql, "u1") == sql


# ──────────── 输出清洗 _unwrap_sql:剥 markdown 代码围栏（回归 /debug #2）────────────
# 模型把 SQL 包进 ```sql … ``` 时，旧的 strip("`") 会残留 `sql\n` 语言标记让 gate 误判。


def test_unwrap_fenced_with_language_tag_passes_gate():
    """```sql 围栏剥净后能过 gate（修复前残留 'sql\\n' 前缀 → 被判非 SELECT）。"""
    raw = "```sql\nSELECT date, protein FROM daily_intake WHERE user_id = 'u1'\n```"
    cleaned = _unwrap_sql(raw)
    assert cleaned.startswith("SELECT")
    assert assert_safe_sql(cleaned, "u1") == cleaned


@pytest.mark.parametrize("raw,expected", [
    ("SELECT 1 FROM vitals WHERE user_id='u1'", "SELECT 1 FROM vitals WHERE user_id='u1'"),  # 纯净
    ("`SELECT 1`", "SELECT 1"),                                    # 单反引号
    ("```\nSELECT 1\n```", "SELECT 1"),                            # 无语言标记围栏
    ("```sql\nSELECT 1\n```", "SELECT 1"),                         # 带语言标记
    ("这是查询：\n```sql\nSELECT 1\n```", "SELECT 1"),             # 围栏前有前言
])
def test_unwrap_variants(raw, expected):
    assert _unwrap_sql(raw) == expected
