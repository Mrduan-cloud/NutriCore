"""NRS2002 报告 PDF → MinIO 归档往返(集成测试,需在线 MinIO)。

固化 W04 缺口的「待核」:render_pdf → archive_report 上传 MinIO → presigned_url 取回,
验证下载到的就是合法 PDF。不在 CI allowlist;MinIO 不可用时自动 skip。
跑法:栈起好后 `pytest tests/test_screening_report_live.py -v`(容器内或本机)。
"""
from __future__ import annotations

import asyncio
import urllib.request

import pytest

from app.agents.risk_screening.schemas import NRSReport


def _minio_ready() -> bool:
    try:
        from app.core.storage import is_healthy

        return is_healthy()
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _minio_ready(), reason="需要在线 MinIO")

_REPORT = NRSReport(
    user_id="e2e-screening", nutrition_score=1, disease_score=0, age_score=0,
    total_score=1, risk_level="暂无营养风险",
    recommendation="建议持续监测体重与进食情况。", answered_at="2026-06-14T10:00:00Z",
)


def test_archive_then_download_roundtrip():
    from app.agents.risk_screening.report import archive_report
    from app.core.storage import presigned_url

    key = asyncio.run(archive_report(_REPORT))
    assert key.startswith("reports/risk/e2e-screening/") and key.endswith(".pdf")

    url = asyncio.run(presigned_url(key, expire_seconds=120))
    with urllib.request.urlopen(url, timeout=20) as resp:
        body = resp.read()
    assert body[:5] == b"%PDF-", "下载回来的不是合法 PDF"
    assert len(body) > 1500
