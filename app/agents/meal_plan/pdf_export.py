"""PDF 方案导出：食材引用 / 营养素配比 / 热量分布。"""
from __future__ import annotations

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.core.storage import upload_object

_FONT_REGISTERED = False


def _ensure_font() -> str:
    global _FONT_REGISTERED
    if not _FONT_REGISTERED:
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        _FONT_REGISTERED = True
    return "STSong-Light"


def _render_day(day: dict, body, h2, font) -> list:
    story: list = [Paragraph(f"第 {day['day']} 天", h2)]
    macros = day.get("macros", {})
    story.append(Paragraph(
        f"总热量：{day.get('total_kcal', '?')} kcal　|　"
        f"碳水 {int((macros.get('carb', 0) or 0) * 100)}% · "
        f"蛋白质 {int((macros.get('protein', 0) or 0) * 100)}% · "
        f"脂肪 {int((macros.get('fat', 0) or 0) * 100)}%",
        body,
    ))
    story.append(Spacer(1, 8))

    for slot_name, slot_key in (("早餐", "breakfast"), ("午餐", "lunch"), ("晚餐", "dinner"), ("加餐", "snack")):
        items = day.get(slot_key) or []
        if not items:
            continue
        rows = [[slot_name + " · 食材", "克数", "热量 (kcal)", "引用"]]
        for it in items:
            rows.append([
                it.get("name", ""),
                str(it.get("portion_g", "")),
                str(it.get("kcal", "")),
                ", ".join(it.get("citations", []))[:60],
            ])
        t = Table(rows, colWidths=[6 * cm, 2 * cm, 2.5 * cm, 6 * cm])
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), font),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e0e7ff")),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#94a3b8")),
        ]))
        story.append(t)
        story.append(Spacer(1, 8))
    return story


def render_meal_plan_pdf(plan: dict) -> bytes:
    font = _ensure_font()
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        rightMargin=2 * cm, leftMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm,
        title=f"NutriCore 营养方案 - {plan.get('user_id', '')}",
    )

    styles = getSampleStyleSheet()
    title = ParagraphStyle("ZhTitle", parent=styles["Title"], fontName=font, fontSize=20,
                           alignment=TA_CENTER, textColor=colors.HexColor("#1f2937"))
    h2 = ParagraphStyle("ZhH2", parent=styles["Heading2"], fontName=font, fontSize=14,
                        textColor=colors.HexColor("#2563eb"))
    body = ParagraphStyle("ZhBody", parent=styles["BodyText"], fontName=font, fontSize=11, leading=18)

    story: list = [
        Paragraph("NutriCore · 7 天个性化营养方案", title),
        Spacer(1, 12),
        Paragraph(
            f"用户：{plan.get('user_id', '')}　|　方案 ID：{plan.get('plan_id', '')}　|　"
            f"目标日热量：{plan.get('target_kcal', '?')} kcal",
            body,
        ),
        Spacer(1, 16),
    ]
    for day in plan.get("days", []) or []:
        story.extend(_render_day(day, body, h2, font))
        story.append(PageBreak())

    doc.build(story)
    return buf.getvalue()


async def export_meal_plan_pdf(plan: dict, user_id: str) -> str:
    pdf_bytes = render_meal_plan_pdf(plan)
    key = f"plans/{user_id}/{plan.get('plan_id', 'latest')}.pdf"
    await upload_object(key, pdf_bytes, content_type="application/pdf")
    return key
