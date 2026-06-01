<script setup lang="ts">
import { ref, onMounted, computed } from "vue";
import { useRoute } from "vue-router";
import { NSpin, NTag } from "naive-ui";
import axios from "axios";
import MarkdownIt from "markdown-it";
import EchartBlock from "@/components/EchartBlock.vue";
import { annotateGlossary } from "@/utils/glossary";

const md = new MarkdownIt({ html: false, linkify: true, breaks: false });
function renderAnswer(text: string): string {
  return annotateGlossary(md.render(text || ""));
}

interface Snapshot {
  token: string;
  question: string;
  answer: string;
  intent?: string | null;
  citations?: string[];
  charts?: Array<{ type: string; label: string; option: Record<string, any> }> | null;
  chart_type?: string | null;
  view_count: number;
  created_at?: string | null;
}

const route = useRoute();
const loading = ref(true);
const snap = ref<Snapshot | null>(null);
const errorMsg = ref("");

const intentLabel: Record<string, string> = {
  consult: "营养咨询",
  screening: "风险筛查",
  plan: "膳食方案",
  insight: "数据洞察",
  risk_alert: "健康提示",
};

const activeChartType = ref("");
function activeOption(): Record<string, any> | null {
  const s = snap.value;
  if (!s?.charts?.length) return null;
  const t = activeChartType.value || s.chart_type || s.charts[0].type;
  return (s.charts.find((c) => c.type === t) || s.charts[0]).option;
}

const SOURCE_LABELS: Record<string, string> = {
  food_composition_excerpt: "食材成分库",
  dietary_guide_2022_excerpt: "《中国居民膳食指南 2022》",
  dietary_guide_2022: "《中国居民膳食指南 2022》",
};
function prettyCitations(raw: string[]): string[] {
  const names = new Set<string>();
  for (const c of raw || []) {
    const docId = String(c).split(":")[0].split("#")[0].trim();
    names.add(SOURCE_LABELS[docId] || docId);
  }
  return [...names];
}

const createdAt = computed(() => {
  if (!snap.value?.created_at) return "";
  try {
    return new Date(snap.value.created_at).toLocaleString("zh-CN", { hour12: false });
  } catch {
    return snap.value.created_at;
  }
});

onMounted(async () => {
  const token = route.params.token as string;
  try {
    const { data } = await axios.get(`/api/share/${encodeURIComponent(token)}`);
    snap.value = data;
  } catch (e: any) {
    errorMsg.value = e?.response?.status === 404 ? "分享内容不存在或已过期" : "加载失败,请稍后再试";
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <div class="share-wrap">
    <header class="share-bar">
      <div class="brand">
        <span class="logo">🥗</span>
        <span class="name">NutriCore</span>
        <span class="sub">AI 营养健康多智能体</span>
      </div>
      <a class="visit-btn" href="/login">体验完整版 →</a>
    </header>

    <main class="share-main">
      <n-spin v-if="loading" />

      <div v-else-if="errorMsg" class="error">
        <div class="error-icon">
          <svg viewBox="0 0 24 24" width="40" height="40" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
            <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
          </svg>
        </div>
        <div class="error-msg">{{ errorMsg }}</div>
        <a class="visit-btn" href="/login">进入 NutriCore 重新提问 →</a>
      </div>

      <div v-else-if="snap" class="snap">
        <div class="question">
          <div class="q-label">问</div>
          <div class="q-body">{{ snap.question }}</div>
        </div>

        <div class="answer">
          <div class="meta">
            <n-tag v-if="snap.intent" size="small" type="success" :bordered="false">
              {{ intentLabel[snap.intent] || snap.intent }}
            </n-tag>
            <span class="meta-time">· {{ createdAt }}</span>
            <span class="meta-spacer" />
            <span class="views">
              <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z" />
                <circle cx="12" cy="12" r="3" />
              </svg>
              {{ snap.view_count }} 次访问
            </span>
          </div>
          <div class="markdown" v-html="renderAnswer(snap.answer || '')" />

          <div v-if="snap.charts && snap.charts.length" class="chart-block">
            <div v-if="snap.charts.length > 1" class="chart-tabs">
              <button
                v-for="c in snap.charts"
                :key="c.type"
                type="button"
                class="chart-tab"
                :class="{ active: (activeChartType || snap.chart_type || snap.charts[0].type) === c.type }"
                @click="activeChartType = c.type"
              >
                {{ c.label }}
              </button>
            </div>
            <echart-block :option="activeOption()" />
          </div>

          <div v-if="snap.citations && snap.citations.length" class="cites">
            <span class="cites-label">
              <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
                <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
              </svg>
              依据来源
            </span>
            <span v-for="c in prettyCitations(snap.citations)" :key="c" class="cite">{{ c }}</span>
          </div>
        </div>

        <footer class="share-foot">
          这是 NutriCore 生成的公开分享 · 不展示提问者身份和健康档案 ·
          <a href="/login">进入完整版,亲自体验 AI 营养师</a>
        </footer>
      </div>
    </main>
  </div>
</template>

<style scoped>
.share-wrap {
  min-height: 100%;
  background: #eef3f2;
  display: flex;
  flex-direction: column;
}
.share-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 24px;
  background: linear-gradient(120deg, #1f5f5e, #2f8b89);
  color: #fff;
}
.brand {
  display: flex;
  align-items: baseline;
  gap: 10px;
}
.brand .logo {
  font-size: 22px;
}
.brand .name {
  font-size: 18px;
  font-weight: 800;
}
.brand .sub {
  font-size: 12.5px;
  opacity: 0.82;
}
.visit-btn {
  font-size: 13.5px;
  color: #fff;
  background: rgba(255, 255, 255, 0.14);
  border: 1px solid rgba(255, 255, 255, 0.32);
  padding: 6px 14px;
  border-radius: 999px;
  text-decoration: none;
}
.visit-btn:hover {
  background: rgba(255, 255, 255, 0.22);
}
.share-main {
  flex: 1;
  max-width: 1000px;
  width: 100%;
  margin: 0 auto;
  padding: 28px 24px 60px;
}
.error {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 60px 12px;
  color: #5b736f;
}
.error-icon {
  color: #9bb3af;
  opacity: 0.7;
}
.error .visit-btn {
  color: #2f8b89;
  background: #fff;
  border-color: #cfe1de;
}
.error .visit-btn:hover {
  background: #f3fbfa;
}
.snap {
  display: flex;
  flex-direction: column;
  gap: 18px;
}
.question {
  display: flex;
  gap: 12px;
  background: linear-gradient(135deg, #34948f 0%, #2a7d79 100%);
  color: #fff;
  padding: 14px 18px;
  border-radius: 14px;
  box-shadow: 0 6px 18px rgba(42, 125, 121, 0.22);
}
.q-label {
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.22);
  font-size: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: 2px;
}
.q-body {
  line-height: 1.7;
  font-size: 16px;
  white-space: pre-wrap;
}
.answer {
  color: #1f333a;
  padding: 4px;
  font-size: 16px;
  line-height: 1.78;
}
.meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  font-size: 12.5px;
  color: #6b8b88;
  flex-wrap: wrap;
}
.meta-spacer {
  flex: 1 1 auto;
}
.views {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #8a9b98;
}
.markdown :deep(h1),
.markdown :deep(h2),
.markdown :deep(h3),
.markdown :deep(h4) {
  font-size: 16.5px;
  font-weight: 700;
  margin: 18px 0 8px;
  color: #14403f;
}
.markdown :deep(p) {
  margin: 8px 0;
}
.markdown :deep(ul),
.markdown :deep(ol) {
  margin: 6px 0;
  padding-left: 22px;
}
.markdown :deep(li) {
  margin: 5px 0;
  line-height: 1.72;
}
.markdown :deep(strong) {
  color: #14403f;
}
/* 术语释义 hover 小贴士(与对话页一致) */
.markdown :deep(.gloss) {
  position: relative;
  border-bottom: 1px dashed #59a39c;
  cursor: help;
  outline: none;
}
.markdown :deep(.gloss)::after {
  content: attr(data-tip);
  position: absolute;
  left: 0;
  top: calc(100% + 9px);
  width: max-content;
  max-width: 280px;
  background: #14403f;
  color: #eaf6f4;
  font-size: 12.5px;
  line-height: 1.62;
  text-align: left;
  padding: 9px 12px;
  border-radius: 10px;
  box-shadow: 0 10px 26px rgba(8, 30, 29, 0.3);
  white-space: normal;
  opacity: 0;
  transform: translateY(-4px);
  transition: opacity 0.15s ease, transform 0.15s ease;
  pointer-events: none;
  z-index: 30;
}
.markdown :deep(.gloss):hover::after,
.markdown :deep(.gloss):focus::after {
  opacity: 1;
  transform: translateY(0);
}
.chart-block {
  margin-top: 12px;
  background: #fff;
  border: 1px solid #eef2f1;
  border-radius: 12px;
  padding: 12px;
}
.chart-tabs {
  display: flex;
  gap: 6px;
  margin-bottom: 8px;
}
.chart-tab {
  background: #f3faf9;
  border: 1px solid #d6e9e7;
  color: #2f8b89;
  font-size: 12.5px;
  padding: 4px 11px;
  border-radius: 999px;
  cursor: pointer;
}
.chart-tab.active {
  background: #2f8b89;
  color: #fff;
  border-color: #2f8b89;
}
.cites {
  margin-top: 14px;
  padding-top: 10px;
  border-top: 1px dashed #d8e5e3;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  font-size: 12.5px;
}
.cites-label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: #9ca3af;
}
.cite {
  color: #2f8b89;
  background: #eef6f5;
  padding: 2px 8px;
  border-radius: 999px;
}
.share-foot {
  margin-top: 18px;
  padding: 16px;
  border-top: 1px solid #e0eae8;
  font-size: 13px;
  color: #8a9b98;
  text-align: center;
  line-height: 1.7;
}
.share-foot a {
  color: #2f8b89;
  text-decoration: none;
  font-weight: 600;
  margin-left: 4px;
}
.share-foot a:hover {
  text-decoration: underline;
}
</style>
