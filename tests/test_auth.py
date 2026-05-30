"""认证安全核心单测 —— 纯逻辑,无 DB / 网络。

覆盖三块:口令哈希(bcrypt)、登录失败锁定判定、用户名/口令策略。
DB 落库的登录/注册/管理流走 docker 栈端到端验证,这里只守逻辑闸门。
"""
from app.auth.passwords import hash_password, verify_password
from app.auth.security import (
    MAX_PASSWORD_LEN,
    MIN_PASSWORD_LEN,
    lock_state,
    next_locked_until,
    password_error,
    username_error,
)

# ---- 口令哈希 ----

def test_hash_is_salted_and_verifiable():
    h = hash_password("s3cret-pw")
    assert h != "s3cret-pw"  # 绝不明文落库
    assert verify_password("s3cret-pw", h) is True
    assert verify_password("wrong", h) is False


def test_hash_is_random_per_call():
    assert hash_password("same") != hash_password("same")  # 每次盐不同


def test_verify_handles_corrupt_hash():
    assert verify_password("x", "not-a-bcrypt-hash") is False
    assert verify_password("x", "") is False


def test_long_password_not_truncated_by_72_byte_limit():
    # bcrypt 原生只取前 72 字节;预散列后两个只差尾部的超长口令应可区分
    base = "A" * 72
    h = hash_password(base + "_tail_one")
    assert verify_password(base + "_tail_one", h) is True
    assert verify_password(base + "_tail_two", h) is False


# ---- 失败锁定(纪元秒,整数比较) ----

def test_not_locked_when_until_is_none_or_past():
    now = 1_000_000.0
    assert lock_state(None, now).locked is False
    assert lock_state(now - 60, now).locked is False


def test_locked_within_window_reports_retry_minutes():
    now = 1_000_000.0
    ls = lock_state(now + 90, now)  # 还剩 90 秒
    assert ls.locked is True
    assert ls.retry_after_minutes == 2  # 90s 向上取整 → 2 分钟


def test_next_locked_until_triggers_only_at_threshold():
    now = 1_000_000.0
    # 未达阈值不锁
    assert next_locked_until(4, 5, 15, now) is None
    # 达到阈值锁 15 分钟
    assert next_locked_until(5, 5, 15, now) == int(now + 15 * 60)


# ---- 用户名策略 ----

def test_username_accepts_chinese_and_ascii():
    assert username_error("李哲") is None
    assert username_error("lin_yue-01") is None


def test_username_rejects_empty_space_and_symbols():
    assert username_error("") is not None
    assert username_error("   ") is not None
    assert username_error("bad name") is not None  # 空格
    assert username_error("drop;table") is not None  # 分号
    assert username_error("a" * 33) is not None  # 超长


# ---- 口令策略 ----

def test_password_policy_bounds():
    assert password_error("a" * MIN_PASSWORD_LEN) is None
    assert password_error("a" * (MIN_PASSWORD_LEN - 1)) is not None
    assert password_error("a" * MAX_PASSWORD_LEN) is None
    assert password_error("a" * (MAX_PASSWORD_LEN + 1)) is not None
