"""NRS-2002 对话式采集:LLM 只做「槽位抽取」,评分交给确定性计算。

职责分工(关键):
- **LLM**:把【档案 + 对话】归类成离散槽位(体重下降档 / 进食量档 / 疾病严重度档),
  这是自然语言理解,适合 LLM。
- **Python(compute_nrs2002)**:把槽位映射成结构化 ``NRSAnswer`` 后,用固定规则
  **确定性计算** NRS-2002 分数。分数不经过 LLM 算术,可复现、可单测、口径一致。

流程:抽取槽位 → 仍有缺失则就该项发问(带可点选项)→ 全部齐了就算分并格式化。
"""
from __future__ import annotations

import json
import re
from typing import Any

from loguru import logger

from app.agents.risk_screening.nrs2002 import compute_nrs2002, nutrition_breakdown
from app.agents.risk_screening.schemas import DiseaseSeverity, NRSAnswer
from app.core.llm import chat_complete

# ---- 槽位枚举 ----
_WL_BANDS = ("none", "gt5_3mo", "gt5_2mo", "gt5_1mo")
_INTAKE_BANDS = ("normal", "p50_75", "p25_50", "p0_25")
_DISEASE_BANDS = ("none", "mild", "moderate", "severe")

# 槽位档位 → NRSAnswer 的结构化取值(取该档的代表值,落入对应分数区间)
_WL_TO_ANSWER: dict[str, tuple[float, int]] = {  # band -> (pct, period_months)
    "none": (0.0, 3),
    "gt5_3mo": (6.0, 3),
    "gt5_2mo": (6.0, 2),
    "gt5_1mo": (6.0, 1),
}
_INTAKE_TO_DROP: dict[str, float] = {  # band -> 进食量下降百分比
    "normal": 0.0,
    "p50_75": 38.0,  # 进食≈平时 62% → 下降≈38% → 1 分
    "p25_50": 63.0,  # 进食≈平时 37% → 下降≈63% → 2 分
    "p0_25": 88.0,  # 进食≈平时 12% → 下降≈88% → 3 分
}
_DISEASE_TO_SEVERITY: dict[str, DiseaseSeverity] = {
    "none": DiseaseSeverity.NONE,
    "mild": DiseaseSeverity.MILD,
    "moderate": DiseaseSeverity.MODERATE,
    "severe": DiseaseSeverity.SEVERE,
}

# 各槽位缺失时的固定问题 + 可点选项(顺序与档位一一对应,便于用户点选后回填)
SLOT_QUESTIONS: dict[str, dict[str, Any]] = {
    "weight_loss_band": {
        "message": "**近 1-3 个月**体重有没有明显下降?(相对原体重)",
        "quick_replies": [
            "基本没下降(<5%)",
            "近 3 个月下降 >5%",
            "近 2 个月下降 >5%",
            "近 1 个月下降 >5%",
        ],
    },
    "intake_band": {
        "message": "**近一周**进食量大约是平时的多少?",
        "quick_replies": [
            "跟平时差不多(>75%)",
            "约平时的 50-75%",
            "约平时的 25-50%",
            "几乎吃不下(0-25%)",
        ],
    },
    "disease_band": {
        "message": "目前有没有急性疾病或重大应激?(如大手术、感染、肿瘤、卒中)",
        "quick_replies": [
            "没有 / 仅稳定慢性病",
            "慢病急性并发症 / 肿瘤",
            "腹部大手术 / 卒中等",
            "ICU / 重型创伤",
        ],
    },
}

_EXTRACT_SYSTEM = """你是 NRS-2002 槽位抽取器。阅读【已知信息】和【对话记录】,
把用户已提供或可明确推断的信息映射到下列槽位;**无法确定的一律填 "unknown"**。

槽位与取值:
- weight_loss_band(近 1-3 个月体重下降):
  - "none": 下降 <5% 或 无明显下降
  - "gt5_3mo": 近 3 个月下降 >5%
  - "gt5_2mo": 近 2 个月下降 >5%
  - "gt5_1mo": 近 1 个月下降 >5%(或近 3 个月 >15%)
  - 仅有最近几天/一两周的体重记录,不足以判断 1-3 个月趋势时,填 "unknown"
- intake_band(近一周进食量占平时比例):
  - "normal": >75%   "p50_75": 50-75%   "p25_50": 25-50%   "p0_25": 0-25%
- disease_band(急性疾病 / 应激严重度):
  - "none": 无急性疾病,或仅稳定慢性病(如稳定的高血压 / 糖尿病)
  - "mild": 慢病急性并发症 / 肿瘤 / 髋骨折   "moderate": 腹部大手术 / 卒中 / 重症肺炎
  - "severe": 重型颅脑损伤 / 骨髓移植 / ICU 重症

只输出严格 JSON:{"weight_loss_band":"...","intake_band":"...","disease_band":"..."}
只输出 JSON 对象。"""


def _extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}


def _format_known(profile: dict[str, Any]) -> str:
    """可用于槽位抽取的「已知信息」。

    注意:**不放近期体重趋势**——它通常只有十来天,不足以判断 NRS-2002 的近 1-3 个月
    体重变化;若放进来,LLM 容易据此把 weight_loss_band 误填成 "none",导致「没问体重
    却判无下降」。体重一项一律向用户确认(趋势仅在提问时作为友好提示展示)。
    """
    parts: list[str] = []
    age = profile.get("age")
    if age is not None:
        parts.append(f"年龄:{age} 岁")
    cd = profile.get("chronic_diseases") or []
    parts.append(f"慢性病史:{'、'.join(map(str, cd)) if cd else '无记录'}")
    bmi = profile.get("bmi")
    if bmi:
        parts.append(f"BMI:{bmi}")
    return "\n".join(f"- {p}" for p in parts)


async def _extract_slots(known: str, conversation: str) -> dict[str, str]:
    prompt = f"【已知信息】\n{known}\n\n【对话记录】\n{conversation}"
    raw = await chat_complete(
        prompt, system=_EXTRACT_SYSTEM, response_format="json", temperature=0.0, max_tokens=200
    )
    data = _extract_json(raw)
    out: dict[str, str] = {}
    for slot, valid in (
        ("weight_loss_band", _WL_BANDS),
        ("intake_band", _INTAKE_BANDS),
        ("disease_band", _DISEASE_BANDS),
    ):
        v = data.get(slot)
        out[slot] = v if v in valid else "unknown"
    return out


_WL_DESC = {
    "none": "无明显下降(<5%)",
    "gt5_3mo": "近 3 个月下降 >5%",
    "gt5_2mo": "近 2 个月下降 >5%",
    "gt5_1mo": "近 1 个月下降 >5%",
}
_INTAKE_DESC = {
    "normal": "与平时相近(>75%)",
    "p50_75": "平时的 50-75%",
    "p25_50": "平时的 25-50%",
    "p0_25": "几乎吃不下(0-25%)",
}
_DISEASE_DESC = {
    "none": "无急性疾病 / 仅稳定慢性病",
    "mild": "慢病急性并发症 / 肿瘤",
    "moderate": "腹部大手术 / 卒中等",
    "severe": "ICU / 重型创伤",
}


def _bmi_label(bmi: float) -> str:
    """中国成人 BMI 分级(WS/T 428-2013)。

    跟 NRS-2002 评分逻辑解耦:评分关心的是营养不良风险(<18.5 / <20.5 才扣分),
    标签关心的是常识沟通(超重 / 肥胖也得说清,不能笼统称"正常")。
    """
    if bmi < 18.5:
        return "偏瘦"
    if bmi < 24:
        return "正常"
    if bmi < 28:
        return "超重"
    return "肥胖"


def _next_screen_hint(total: int) -> str:
    """NRS-2002 复评节奏:有风险 / 暂无风险 / 全 0 分。"""
    if total >= 3:
        return "**下次复评:** 营养支持方案启动后 1 周复评。"
    if total >= 1:
        return "**下次复评:** 1 周后再做一次(NRS-2002 标准做法),密切跟踪。"
    return "**下次复评:** 半年至 1 年内复测即可;体重 / 进食量有明显变化时立即重做。"


def _weak_spot_advice(parts: dict[str, int], slots: dict[str, str]) -> list[str]:
    """按实际扣分维度给出针对性建议;不扣分则不出条(避免空泛)。"""
    advice: list[str] = []
    if parts.get("intake", 0) >= 1:
        advice.append(
            f"**进食量不足({_INTAKE_DESC.get(slots.get('intake_band', ''), '')})** —— "
            "从加餐入手(上午 / 下午各 1 次),选高能量密度小食(无糖酸奶、坚果、全脂奶);"
            "每餐先吃蛋白质 + 主食、最后吃菜,避免过早饱腹。"
        )
    if parts.get("weight_loss", 0) >= 1:
        advice.append(
            f"**体重下降({_WL_DESC.get(slots.get('weight_loss_band', ''), '')})** —— "
            "每天同一时间(晨起空腹)称重并记录 2 周趋势;若仍持续下降,"
            "需排查甲状腺、糖代谢、消化吸收等基础病因。"
        )
    if parts.get("bmi", 0) >= 1:
        advice.append(
            "**BMI 偏低** —— 优先抬高每日总热量(以蛋白质 + 复合碳水为主),"
            "配合阻力训练增肌,而不只是堆脂肪。"
        )
    return advice


def _completion_quick_replies(total: int, parts: dict[str, int]) -> list[str]:
    """评分后的入口建议,按风险等级 + 扣分维度组合。"""
    if total >= 3:
        return [
            "立即生成 7 天营养支持方案",
            "解释这些分数的含义",
            "什么时候需要找临床营养师?",
        ]
    if total >= 1:
        replies: list[str] = []
        if parts.get("intake", 0) >= 1:
            replies.append("如何科学地提升进食量?")
        if parts.get("weight_loss", 0) >= 1:
            replies.append("体重持续下降可能是什么原因?")
        replies += ["生成 7 天营养方案", "解释每个分数的含义"]
        return replies[:4]
    return ["生成 7 天保养型食谱", "解释每个分数的含义"]


def _format_result(report, slots: dict[str, str], answer: NRSAnswer) -> str:
    parts = nutrition_breakdown(answer)
    age_note = "≥70,+1 分" if answer.age >= 70 else "<70,0 分"

    lines = [
        "### NRS-2002 评分结果(确定性计算)",
        "",
        f"**A. 营养状态受损:{report.nutrition_score} 分**",
        f"- 体重:{_WL_DESC.get(slots['weight_loss_band'], '未知')} → {parts['weight_loss']} 分",
        f"- 进食:{_INTAKE_DESC.get(slots['intake_band'], '未知')} → {parts['intake']} 分",
        f"- BMI {answer.bmi}({_bmi_label(answer.bmi)}) → {parts['bmi']} 分",
        f"- 取三者最高 → {report.nutrition_score} 分",
        "",
        f"**B. 疾病严重程度:{report.disease_score} 分** — {_DISEASE_DESC.get(slots['disease_band'], '未知')}",
        "",
        f"**C. 年龄:{report.age_score} 分** — {answer.age} 岁({age_note})",
        "",
        f"**总分:{report.total_score} 分 → {report.risk_level}**",
        report.recommendation,
        "",
        _next_screen_hint(report.total_score),
    ]

    advice = _weak_spot_advice(parts, slots)
    if advice:
        lines.append("")
        lines.append("**针对性建议**")
        for a in advice:
            lines.append(f"- {a}")

    lines += [
        "",
        "> 本结果由 NRS-2002 算法确定性计算,属初步筛查、非诊断;"
        "涉及疾病诊疗 / 用药请咨询专科医生或临床营养师。",
    ]
    return "\n".join(lines)


def _ask(slot: str, hint: str = "") -> dict[str, Any]:
    q = SLOT_QUESTIONS[slot]
    msg = (hint + "\n\n" + q["message"]) if hint else q["message"]
    return {"message": msg, "quick_replies": list(q["quick_replies"]), "complete": False}


async def screen_step(
    profile: dict[str, Any], conversation: str, weight_trend: dict | None, user_id: str
) -> dict[str, Any]:
    """推进一步 NRS-2002:返回 {message, quick_replies, complete}。

    - 仍有关键槽位缺失 → 就该项发问(带可点选项)
    - 槽位齐全 → 用 compute_nrs2002 确定性算分并格式化
    """
    known = _format_known(profile)
    slots = await _extract_slots(known, conversation)

    if slots.get("weight_loss_band", "unknown") == "unknown":
        # 体重必须用户确认;近期体重记录(若有)仅作友好提示,不参与判分
        hint = ""
        if weight_trend:
            hint = (
                f"_(系统记录:近 {weight_trend['days']} 天体重 "
                f"{weight_trend['first']}→{weight_trend['last']} kg,基本稳定;"
                f"营养筛查看的是近 1-3 个月,请据此回答)_"
            )
        return _ask("weight_loss_band", hint)
    for slot in ("intake_band", "disease_band"):
        if slots.get(slot, "unknown") == "unknown":
            return _ask(slot)

    pct, months = _WL_TO_ANSWER[slots["weight_loss_band"]]
    bmi = profile.get("bmi")
    if not bmi:
        # 没有 BMI 时给个中性占位(不触发 BMI 维度计分),仅为构造合法 NRSAnswer
        bmi = 22.0
    answer = NRSAnswer(
        age=int(profile.get("age") or 0),
        bmi=float(bmi),
        weight_loss_pct_3m=pct,
        weight_loss_period_months=months,
        food_intake_drop_pct=_INTAKE_TO_DROP[slots["intake_band"]],
        disease_severity=_DISEASE_TO_SEVERITY[slots["disease_band"]],
    )
    report = compute_nrs2002(user_id, answer)
    logger.bind(user_id=user_id).info(
        "nrs2002 deterministic score: nutrition={} disease={} age={} total={}",
        report.nutrition_score, report.disease_score, report.age_score, report.total_score,
    )
    return {
        "message": _format_result(report, slots, answer),
        "quick_replies": _completion_quick_replies(report.total_score, nutrition_breakdown(answer)),
        "complete": True,
    }
