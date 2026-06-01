/* 营养专业术语释义 —— 给 AI 回答里的 GI / BMI / NRS-2002 等加 hover 小贴士,
   对不懂行的用户更友好。在已渲染的 Markdown HTML 上做 DOM 级文本节点包裹,
   不会破坏标签 / 链接 / 代码块。 */

export const GLOSSARY: Record<string, string> = {
  GI: "血糖生成指数(升糖指数):衡量某种食物升高血糖的快慢。≤55 为低 GI,升糖平稳,利于控糖、控体重。",
  GL: "血糖负荷 = GI × 实际摄入碳水量,同时兼顾「升糖速度」和「吃了多少」,比单看 GI 更全面。",
  BMI: "身体质量指数 = 体重(kg) ÷ 身高²(m)。中国成人标准:18.5–23.9 正常,24–27.9 超重,≥28 肥胖。",
  "NRS-2002": "营养风险筛查 2002:ESPEN 推荐的营养风险筛查工具,综合营养状态 / 疾病 / 年龄打分,总分 ≥3 提示存在营养风险。",
  NRS2002: "营养风险筛查 2002:ESPEN 推荐的营养风险筛查工具,综合营养状态 / 疾病 / 年龄打分,总分 ≥3 提示存在营养风险。",
  TDEE: "每日总能量消耗(Total Daily Energy Expenditure):一天总共消耗的热量,膳食方案的目标热量按它估算。",
  BMR: "基础代谢率:静息状态下维持生命所需的最低热量(呼吸、心跳等),约占每日总消耗的 60–70%。",
};

// 词表按长度降序,确保 "NRS-2002" 先于潜在的 "NRS" 命中;转义正则元字符
const _TERMS = Object.keys(GLOSSARY).sort((a, b) => b.length - a.length);
const _ESCAPED = _TERMS.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
const _MATCH = new RegExp("(" + _ESCAPED.join("|") + ")", "g");
const _SKIP_TAGS = new Set(["CODE", "PRE", "A", "SCRIPT", "STYLE"]);

/** 在已渲染的 Markdown HTML 上,把术语包成可 hover 的 .gloss span。 */
export function annotateGlossary(html: string): string {
  if (typeof window === "undefined" || !window.DOMParser) return html;
  const doc = new DOMParser().parseFromString(html, "text/html");
  const walker = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT);

  // 先收集需要处理的文本节点(遍历中直接改 DOM 会打乱 walker)
  const targets: Text[] = [];
  let node: Node | null;
  while ((node = walker.nextNode())) {
    const text = node.nodeValue || "";
    if (!text.trim()) continue;
    // 跳过代码 / 链接 / 已包裹的术语
    let p: HTMLElement | null = node.parentElement;
    let skip = false;
    while (p) {
      if (_SKIP_TAGS.has(p.tagName) || p.classList?.contains("gloss")) {
        skip = true;
        break;
      }
      p = p.parentElement;
    }
    if (skip) continue;
    _MATCH.lastIndex = 0;
    if (_MATCH.test(text)) targets.push(node as Text);
  }

  for (const t of targets) {
    const s = t.nodeValue || "";
    const frag = doc.createDocumentFragment();
    let last = 0;
    _MATCH.lastIndex = 0;
    let m: RegExpExecArray | null;
    while ((m = _MATCH.exec(s))) {
      const term = m[1];
      if (m.index > last) frag.appendChild(doc.createTextNode(s.slice(last, m.index)));
      const span = doc.createElement("span");
      span.className = "gloss";
      span.setAttribute("data-tip", GLOSSARY[term]);
      span.setAttribute("tabindex", "0");
      span.textContent = term;
      frag.appendChild(span);
      last = m.index + term.length;
    }
    if (last < s.length) frag.appendChild(doc.createTextNode(s.slice(last)));
    t.parentNode?.replaceChild(frag, t);
  }
  return doc.body.innerHTML;
}
