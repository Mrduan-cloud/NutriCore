"""认证安全策略 —— 纯函数,无 DB / IO 依赖,便于离线穷举单测。

把「用户名规范、口令策略、登录失败锁定」三类规则收敛到这里,路由层只负责
把 ORM 行喂进来、按返回值落库。规则与持久化解耦后可被 pytest 直接覆盖。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# 用户名:中文 / 字母 / 数字 / 下划线 / 连字符,1-32 位。
# 允许中文是为了演示人设(李哲 / 林悦)同时充当 user_id。
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_一-鿿-]{1,32}$")

MIN_PASSWORD_LEN = 6
MAX_PASSWORD_LEN = 128


def username_error(username: str) -> str | None:
    """返回不合法原因;合法返回 None。"""
    u = (username or "").strip()
    if not u:
        return "用户名不能为空"
    if not _USERNAME_RE.match(u):
        return "用户名仅支持中文 / 字母 / 数字 / 下划线 / 连字符,长度 1-32"
    return None


def password_error(password: str) -> str | None:
    """返回不合法原因;合法返回 None。"""
    p = password or ""
    if len(p) < MIN_PASSWORD_LEN:
        return f"口令至少 {MIN_PASSWORD_LEN} 位"
    if len(p) > MAX_PASSWORD_LEN:
        return f"口令最多 {MAX_PASSWORD_LEN} 位"
    return None


@dataclass(frozen=True)
class LockState:
    locked: bool
    retry_after_seconds: int = 0

    @property
    def retry_after_minutes(self) -> int:
        # 向上取整,提示「请 N 分钟后再试」更符合直觉
        return (self.retry_after_seconds + 59) // 60


# 锁定截止时间一律用 UTC 纪元秒(int)存取:整数比较无时区歧义,
# 规避 ORM/MySQL DATETIME 在 use_tz 下往返错位 8 小时的坑。

def lock_state(locked_until_ts: int | float | None, now_ts: int | float) -> LockState:
    """根据锁定截止纪元秒判定当前是否处于锁定窗口。"""
    if locked_until_ts is not None and locked_until_ts > now_ts:
        return LockState(True, int(locked_until_ts - now_ts))
    return LockState(False, 0)


def next_locked_until(
    failed_attempts: int, max_attempts: int, lockout_minutes: int, now_ts: int | float
) -> int | None:
    """一次失败「之后」计算新的锁定截止纪元秒。

    达到/超过阈值则锁定一段时间,否则返回 None(不锁定)。
    ``failed_attempts`` 应为本次失败累加后的值。
    """
    if failed_attempts >= max_attempts:
        return int(now_ts + lockout_minutes * 60)
    return None
