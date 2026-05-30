"""基于 ReportLab 渲染 NRS2002 PDF 风险报告，归档 MinIO。"""
from __future__ import annotations

from datetime import datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.agents.risk_screening.schemas import NRSReport
from app.core.storage import upload_object

# 注册中文字体（CID 字体不需要额外文件）
_FONT_REGISTERED = False


def _ensure_font() -> str:
    global _FONT_REGISTERED
    if not _FONT_REGISTERED:
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        _FONT_REGISTERED = True
    return "STSong-Light"


def render_pdf(report: NRSReport) -> bytes:
    font = _ensure_font()
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title=f"NRS2002 营养风险筛查报告 - {report.user_id}",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ZhTitle", parent=styles["Title"], fontName=font, fontSize=20,
        alignment=TA_CENTER, textColor=colors.HexColor("#1f2937"),
    )
    body = ParagraphStyle("ZhBody", parent=styles["BodyText"], fontName=font, fontSize=11, leading=18)
    h2 = ParagraphStyle("ZhH2", parent=styles["Heading2"], fontName=font, fontSize=14,
                        textColor=colors.HexColor("#2563eb"))

    story: list = []
    story.append(Paragraph("NutriCore · NRS2002 营养风险筛查报告", title_style))
    story.append(Spacer(1, 12))
    story.append(Paragraph(f"用户：{report.user_id}　|　报告时间：{report.answered_at}", body))
    story.append(Spacer(1, 12))

    story.append(Paragraph("一、评分明细", h2))
    table_data = [
        ["维度", "得分"],
        ["营养状态", str(report.nutrition_score)],
        ["疾病严重程度", str(report.disease_score)],
        ["年龄 (≥70 加 1)", str(report.age_score)],
        ["合计", str(report.total_score)],
    ]
    table = Table(table_data, colWidths=[8 * cm, 4 * cm])
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font),
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e0e7ff")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#94a3b8")),
        ("ALIGN", (1, 1), (1, -1), "CENTER"),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#fef3c7")),
    ]))
    story.append(table)
    story.append(Spacer(1, 16))

    story.append(Paragraph("二、风险等级与建议", h2))
    risk_color = {"无风险": "#10b981", "存在风险": "#f59e0b", "建议营养支持": "#ef4444"}.get(report.risk_level, "#475569")
    story.append(Paragraph(
        f'<font color="{risk_color}"><b>风险等级：{report.risk_level}</b></font>', body
    ))
    story.append(Paragraph(report.recommendation, body))
    story.append(Spacer(1, 16))

    story.append(Paragraph("三、说明", h2))
    story.append(Paragraph(
        "本报告基于 NRS2002 (Nutrition Risk Screening 2002, Kondrup et al., 2003) 算法生成。"
        "仅作为日常营养健康参考，不能替代临床诊断；如需个性化营养支持方案，"
        "请配合临床医师与注册营养师评估。",
        body,
    ))

    doc.build(story)
    return buf.getvalue()


async def archive_report(report: NRSReport) -> str:
    pdf_bytes = render_pdf(report)
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    object_key = f"reports/risk/{report.user_id}/{ts}.pdf"
    await upload_object(object_key, pdf_bytes, content_type="application/pdf")
    return object_key
