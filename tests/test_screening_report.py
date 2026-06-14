"""NRS2002 PDF 渲染单测 —— 只依赖 ReportLab(已解耦 MinIO),可进 CI。

守护 render_pdf:中文字体注册、三档风险配色分支、Schema 字段拼装不因 ReportLab
版本 / 代码改动悄悄崩。MinIO 归档的真实往返见 test_screening_report_live.py(集成)。
"""
from __future__ import annotations

import pytest

from app.agents.risk_screening.report import render_pdf
from app.agents.risk_screening.schemas import NRSReport


def _report(total: int, risk: str = "暂无营养风险") -> NRSReport:
    return NRSReport(
        user_id="demo-001",
        nutrition_score=min(total, 3),
        disease_score=0,
        age_score=1 if total >= 1 else 0,
        total_score=total,
        risk_level=risk,
        recommendation="建议持续监测体重与进食情况，必要时咨询临床营养师。",
        answered_at="2026-06-14T10:00:00Z",
    )


def test_render_pdf_returns_valid_pdf_bytes():
    pdf = render_pdf(_report(1))
    assert isinstance(pdf, bytes)
    assert pdf[:5] == b"%PDF-"      # PDF 魔数
    assert pdf.rstrip().endswith(b"%%EOF")
    assert len(pdf) > 1500          # 含中文表格,不可能这么小


@pytest.mark.parametrize("total,risk", [
    (0, "暂无营养风险"),    # green 分支
    (2, "暂无营养风险"),    # amber 分支(有扣分但 < 3)
    (4, "有营养风险"),      # red 分支
])
def test_render_pdf_all_risk_color_branches(total, risk):
    pdf = render_pdf(_report(total, risk))
    assert pdf[:5] == b"%PDF-"


def test_render_pdf_font_registration_idempotent():
    # 连续两次渲染(字体只注册一次)不应抛错
    a = render_pdf(_report(0))
    b = render_pdf(_report(3, "有营养风险"))
    assert a[:5] == b"%PDF-" and b[:5] == b"%PDF-"
