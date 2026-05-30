<script setup lang="ts">
import { ref, computed, nextTick, onMounted } from "vue";
import { useRouter } from "vue-router";
import {
  useMessage,
  NButton,
  NInput,
  NSpin,
  NAvatar,
  NPopconfirm,
  NModal,
} from "naive-ui";
import MarkdownIt from "markdown-it";
import client from "@/api/client";
import { useAuthStore } from "@/stores/auth";
import { useConversationStore, type ChatMessage } from "@/stores/conversations";
import EchartBlock from "@/components/EchartBlock.vue";
import ShareDialog from "@/components/ShareDialog.vue";
import CapIcon from "@/components/CapIcon.vue";
import AgentArt from "@/components/AgentArt.vue";

// Markdown 渲染器:html:false 防 XSS,breaks:false 避免单换行变 <br> 撑大间距
const md = new MarkdownIt({ html: false, linkify: true, breaks: false });
function renderMarkdown(text: string): string {
  return md.render(text || "");
}

// 引用来源 → 友好中文名 + 去重
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

const router = useRouter();
const message = useMessage();
const auth = useAuthStore();
const convStore = useConversationStore();

const input = ref("");
const loading = ref(false);
const listRef = ref<HTMLElement | null>(null);

// 头像:DiceBear,风格可切换(存 auth store / localStorage)
const AVATAR_STYLES = [
  "avataaars",
  "adventurer",
  "fun-emoji",
  "thumbs",
  "bottts",
  "notionists",
  "lorelei",
  "micah",
];
function avatarUrl(style: string): string {
  return `https://api.dicebear.com/9.x/${style}/svg?seed=${encodeURIComponent(
    auth.userId || "demo",
  )}&backgroundColor=b6e3f4,c0aede,ffd5dc`;
}
const userAvatar = computed(() => avatarUrl(auth.avatarStyle));

const showAvatarPicker = ref(false);
function pickAvatar(style: string) {
  auth.setAvatarStyle(style);
  showAvatarPicker.value = false;
}

// 当前会话的消息 —— 纯读取,不在 computed 里产生副作用(之前调用 active()
// 会在渲染期间改写 activeId / 新建会话,可能触发 "Maximum recursive updates" 卡死)。
const messages = computed<ChatMessage[]>(() => {
  const conv =
    convStore.list.find((c) => c.id === convStore.activeId) || convStore.list[0];
  return conv ? conv.messages : [];
});

// 4 个子 Agent 的能力入口 —— key 与后端 intent 对齐,点击即发起一句代表性提问,
// 由后端 intent_router 自动派发到对应子 Agent(答案上会贴意图标签印证路由)。
const capabilities = [
  {
    key: "consult",
    name: "营养咨询",
    desc: "低 GI 主食、三餐搭配、营养知识",
    prompt: "低 GI 的主食有哪些推荐?",
  },
  {
    key: "screening",
    name: "风险筛查",
    desc: "NRS-2002 营养风险评估",
    prompt: "帮我做一次 NRS2002 营养风险筛查",
  },
  {
    key: "plan",
    name: "膳食方案",
    desc: "7 天个性化食谱",
    prompt: "帮我生成一份七天减脂食谱",
  },
  {
    key: "insight",
    name: "数据洞察",
    desc: "近 30 天体重 / 营养趋势",
    prompt: "分析我近30天的蛋白质达标情况",
  },
];

function fillPrompt(text: string) {
  input.value = text;
}

// 数据洞察:当前选中图的 option(多图切换)
function activeChart(m: ChatMessage): Record<string, any> | null {
  if (m.charts && m.charts.length) {
    const t = m.chartType || m.charts[0].type;
    return (m.charts.find((c) => c.type === t) || m.charts[0]).option;
  }
  return m.chart || null;
}

// 复制工具:secure context 用 Clipboard API,否则回退 execCommand
async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
    } else {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    }
    return true;
  } catch {
    return false;
  }
}

async function copyMessage(m: ChatMessage) {
  const ok = await copyText(m.content || "");
  if (ok) message.success("已复制");
  else message.warning("复制失败,请手动选择");
}

// 找到这条 assistant 回复对应的、紧邻其前的用户提问
function priorUserMessage(m: ChatMessage): ChatMessage | null {
  const conv = convStore.list.find((c) => c.id === convStore.activeId);
  if (!conv) return null;
  const idx = conv.messages.indexOf(m);
  for (let i = idx - 1; i >= 0; i--) {
    if (conv.messages[i].role === "user") return conv.messages[i];
  }
  return null;
}

// 分享:走后端 POST /api/chat/share → 拿到不可猜 token → 打开渠道选择弹窗。
// 公开页 /s/{token} 可被任何人(无需登录)看到这一问一答。
const shareOpen = ref(false);
const shareLoading = ref(false);
const shareUrl = ref("");
const shareTitle = ref("");

async function shareMessage(m: ChatMessage) {
  const u = priorUserMessage(m);
  // 快照标题取问题前 60 字,方便社交平台默认文案
  shareTitle.value = (u?.content || m.content || "NutriCore AI 营养师").slice(0, 60);
  shareUrl.value = "";
  shareLoading.value = true;
  shareOpen.value = true;
  try {
    const { data } = await client.post("/api/chat/share", {
      question: u?.content || "",
      answer: m.content || "",
      intent: m.intent || null,
      citations: m.citations || [],
      charts: m.charts && m.charts.length ? m.charts : null,
      chart_type: m.chartType || null,
    });
    // 组装公开 URL(用 window.origin 适配本地/将来部署的不同域名)
    shareUrl.value = `${window.location.origin}${data.path}`;
  } catch (e: any) {
    shareOpen.value = false;
    message.error(e?.response?.data?.detail || "生成分享链接失败,请重试");
  } finally {
    shareLoading.value = false;
  }
}

// 重新生成:只允许在最后一条 assistant 上,否则会破坏后续上下文。
// 实现:回退到对应的用户提问 → 删掉「问+原答」→ 调 send() 重新走一遍流。
async function regenerate(m: ChatMessage) {
  if (loading.value) return;
  const conv = convStore.active();
  const idx = conv.messages.indexOf(m);
  if (idx < 1) return;
  let userIdx = idx - 1;
  while (userIdx >= 0 && conv.messages[userIdx].role !== "user") userIdx--;
  if (userIdx < 0) return;
  const userText = conv.messages[userIdx].content;
  conv.messages.splice(userIdx);
  await send(userText);
}

function rate(m: ChatMessage, value: "up" | "down") {
  // 反复点同一档 = 取消;切换档位则覆盖
  m.rating = m.rating === value ? undefined : value;
  convStore.save();
  if (m.rating === "up") message.success("感谢反馈 👍");
  else if (m.rating === "down") message.info("已记录,我们会改进 🙏");

  // 落审计日志(fire-and-forget):上报失败也不影响本地 rating
  if (m.rating) {
    const conv = convStore.active();
    const u = priorUserMessage(m);
    client
      .post("/api/chat/feedback", {
        rating: m.rating,
        session_id: conv.id,
        intent: m.intent || null,
        question: u?.content?.slice(0, 500) || null,
        answer_excerpt: (m.content || "").slice(0, 500),
      })
      .catch(() => {
        /* 静默:本地评分已保存,审计上报失败不打扰用户 */
      });
  }
}

// 左侧栏收起/展开(持久化)
const sidebarCollapsed = ref(localStorage.getItem("nutricore_sidebar_collapsed") === "1");
function toggleSidebar() {
  sidebarCollapsed.value = !sidebarCollapsed.value;
  localStorage.setItem("nutricore_sidebar_collapsed", sidebarCollapsed.value ? "1" : "0");
}

const intentLabel: Record<string, string> = {
  consult: "营养咨询",
  screening: "风险筛查",
  plan: "膳食方案",
  insight: "数据洞察",
  risk_alert: "健康提示",
};

onMounted(() => {
  // 按当前登录用户重载会话(切换账号后不串历史)
  convStore.reload();
  if (convStore.list.length === 0) convStore.newConversation();
  else convStore.active();
});

async function scrollToBottom() {
  await nextTick();
  if (listRef.value) listRef.value.scrollTop = listRef.value.scrollHeight;
}

async function send(text?: string) {
  const content = (text ?? input.value).trim();
  if (!content || loading.value) return;

  const conv = convStore.active();
  // 本轮之前的历史(纯文本、最近 12 条),供后端多轮场景(如 NRS-2002 续轮)
  const history = conv.messages
    .filter((m) => m.content)
    .slice(-12)
    .map((m) => ({ role: m.role, content: m.content }));
  conv.messages.push({ role: "user", content });
  // 占位 assistant 消息,流式往里填;取回 reactive 代理引用
  conv.messages.push({
    role: "assistant",
    content: "",
    citations: [],
    usedTools: [],
    chart: null,
    charts: [],
    chartType: "",
    quickReplies: [],
  });
  const ai = conv.messages[conv.messages.length - 1];
  convStore.save();
  input.value = "";
  loading.value = true;
  scrollToBottom();

  try {
    const resp = await fetch("/api/chat/nutritionist/stream", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${auth.token}`,
      },
      body: JSON.stringify({ message: content, session_id: conv.id, history }),
    });
    if (resp.status === 401) {
      auth.logout();
      router.push("/login");
      return;
    }
    if (!resp.ok || !resp.body) throw new Error("stream " + resp.status);

    const reader = resp.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buf = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      // SSE 事件以空行分隔
      const events = buf.split("\n\n");
      buf = events.pop() || "";
      for (const ev of events) {
        const line = ev.trim();
        if (!line.startsWith("data:")) continue;
        let p: any;
        try {
          p = JSON.parse(line.slice(5).trim());
        } catch {
          continue;
        }
        if (p.type === "meta") {
          ai.intent = p.intent;
          ai.isHighRisk = p.is_high_risk;
        } else if (p.type === "delta") {
          ai.content += p.content;
          scrollToBottom();
        } else if (p.type === "done") {
          ai.citations = p.citations || [];
          ai.usedTools = p.used_tools || [];
          ai.chart = p.chart || null;
          ai.charts = p.charts || [];
          ai.chartType = ai.charts && ai.charts.length ? ai.charts[0].type : "";
          ai.quickReplies = p.quick_replies || [];
        } else if (p.type === "error") {
          ai.content += (ai.content ? "\n\n" : "") + p.message;
        }
      }
    }
    if (!ai.content) ai.content = "（无回复）";
  } catch (e: any) {
    ai.content = ai.content || "抱歉,服务暂时不可用:" + (e?.message || "未知错误");
  } finally {
    convStore.save();
    loading.value = false;
    scrollToBottom();
  }
}

function onNewChat() {
  convStore.newConversation();
  input.value = "";
}

function onSelectConv(id: string) {
  convStore.select(id);
  scrollToBottom();
}

function onDeleteConv(id: string) {
  convStore.remove(id);
  if (convStore.list.length === 0) convStore.newConversation();
}

// 重命名对话(双击标题 / 点 ✎ 进入编辑;Enter 或失焦保存,Esc 取消)
const editingId = ref("");
const editingTitle = ref("");
const renameInput = ref<HTMLInputElement | null>(null);
function startRename(c: { id: string; title: string }) {
  editingId.value = c.id;
  editingTitle.value = c.title || "";
  nextTick(() => renameInput.value?.focus());
}
function commitRename() {
  if (editingId.value && editingTitle.value.trim()) {
    convStore.rename(editingId.value, editingTitle.value);
  }
  editingId.value = "";
}
function cancelRename() {
  editingId.value = "";
}

function onLogout() {
  auth.logout();
  router.push("/login");
}
</script>

<template>
  <div class="layout">
    <!-- ===== 左侧边栏 ===== -->
    <aside class="sidebar" :class="{ collapsed: sidebarCollapsed }">
      <div class="side-brand">
        <span class="logo">🥗</span>
        <div class="side-brand-text">
          <div class="name">NutriCore</div>
          <div class="sub">AI 营养师</div>
        </div>
        <button class="side-collapse" title="收起侧栏" @click="toggleSidebar">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="m11 17-5-5 5-5M18 17l-5-5 5-5" />
          </svg>
        </button>
      </div>

      <n-button class="new-chat" type="primary" block @click="onNewChat">
        ＋ 新对话
      </n-button>

      <div class="conv-list">
        <div class="conv-list-title">历史对话</div>
        <div
          v-for="c in convStore.ordered()"
          :key="c.id"
          class="conv-item"
          :class="{ active: c.id === convStore.activeId, pinned: c.pinned }"
          @click="onSelectConv(c.id)"
        >
          <input
            v-if="editingId === c.id"
            ref="renameInput"
            v-model="editingTitle"
            class="conv-rename"
            maxlength="40"
            @click.stop
            @keyup.enter="commitRename"
            @keyup.esc="cancelRename"
            @blur="commitRename"
          />
          <span v-else class="conv-title" @dblclick.stop="startRename(c)">{{ c.title || "新对话" }}</span>
          <span v-if="editingId !== c.id" class="conv-actions" @click.stop>
            <span class="conv-act" title="重命名" @click="startRename(c)">
              <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <path d="M12 20h9" />
                <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z" />
              </svg>
            </span>
            <span
              class="conv-act conv-pin"
              :class="{ on: c.pinned }"
              :title="c.pinned ? '取消置顶' : '置顶'"
              @click="convStore.togglePin(c.id)"
            >
              <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <path d="M12 17v5" />
                <path d="M9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H8a2 2 0 0 0 0 4 1 1 0 0 1 1 1Z" />
              </svg>
            </span>
            <n-popconfirm @positive-click="onDeleteConv(c.id)">
              <template #trigger>
                <span class="conv-del">
                  <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <path d="M18 6 6 18M6 6l12 12" />
                  </svg>
                </span>
              </template>
              删除这条对话?
            </n-popconfirm>
          </span>
        </div>
      </div>

      <div class="side-user">
        <n-avatar
          round
          :size="30"
          :src="userAvatar"
          color="#e8eef0"
          class="clickable-avatar"
          title="点击更换头像"
          @click="showAvatarPicker = true"
        />
        <span class="uid">{{ auth.userId }}</span>
        <button
          v-if="auth.isAdmin"
          type="button"
          class="logout-btn admin-btn"
          title="管理后台"
          @click="router.push('/admin')"
        >
          后台
        </button>
        <n-popconfirm @positive-click="onLogout">
          <template #trigger>
            <button type="button" class="logout-btn">退出</button>
          </template>
          确定退出登录?
        </n-popconfirm>
      </div>
    </aside>

    <!-- ===== 右侧主对话 ===== -->
    <div class="chat-main">
      <button
        v-if="sidebarCollapsed"
        class="side-expand"
        title="展开侧栏"
        @click="toggleSidebar"
      >
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="m13 17 5-5-5-5M6 17l5-5-5-5" />
        </svg>
      </button>
      <main ref="listRef" class="messages">
        <!-- 欢迎 -->
        <div v-if="messages.length === 0" class="welcome">
          <div class="welcome-logo">🥗</div>
          <h2>你好,我是 NutriCore AI 营养师</h2>
          <p>背后是 4 个协作的专业 Agent,问我任意一句,自动派给最合适的那个 ↓</p>
          <div class="cap-cards">
            <div
              v-for="c in capabilities"
              :key="c.key"
              class="cap-card"
              :class="`theme-${c.key}`"
              @click="send(c.prompt)"
            >
              <div class="cap-art"><agent-art :name="c.key" :size="54" /></div>
              <div class="cap-name">{{ c.name }}</div>
              <div class="cap-desc">{{ c.desc }}</div>
              <div class="cap-try">{{ c.prompt }}</div>
            </div>
          </div>
        </div>

        <!-- 气泡 -->
        <div v-for="(m, i) in messages" :key="i" class="row" :class="m.role">
          <n-avatar v-if="m.role === 'assistant'" round class="avatar" color="#2F8B89">
            🥗
          </n-avatar>
          <div class="bubble" :class="m.role">
            <!-- 用户气泡:复制按钮 hover 浮现在绿色气泡右上角(归属清晰) -->
            <button
              v-if="m.role === 'user' && m.content"
              class="copy-btn user"
              title="复制"
              @click="copyMessage(m)"
            >
              ⧉
            </button>
            <!-- 「营养师思路」过程轨迹 —— LangGraph 多 agent 调度链可视化(Hanako-inspired):
                 intent_router → 子 agent → 工具调用,以灰斜体一行呈现,让多智能体协作"看得见"。 -->
            <div v-if="m.role === 'assistant' && m.intent" class="process-trace">
              <span class="pt-arrow">›</span>
              <span
                class="pt-step"
                :class="{ 'pt-risk': m.isHighRisk }"
              >intent_router → <b>{{ intentLabel[m.intent] || m.intent }}</b></span>
              <template v-for="t in m.usedTools" :key="t">
                <span class="pt-sep">·</span>
                <span class="pt-step">{{ t }}</span>
              </template>
              <span v-if="m.isHighRisk" class="pt-tag pt-tag-risk">高风险</span>
            </div>
            <template v-if="m.role === 'assistant'">
              <div v-if="!m.content" class="thinking">
                <n-spin size="small" /> <span>营养师思考中…</span>
              </div>
              <div v-else class="text markdown" v-html="renderMarkdown(m.content)" />
            </template>
            <div v-else class="text">{{ m.content }}</div>
            <!-- 数据洞察:ECharts 图表(可切换 折线/柱/环形/雷达) -->
            <div
              v-if="m.role === 'assistant' && ((m.charts && m.charts.length) || m.chart)"
              class="chart-block"
            >
              <div v-if="m.charts && m.charts.length > 1" class="chart-tabs">
                <button
                  v-for="c in m.charts"
                  :key="c.type"
                  type="button"
                  class="chart-tab"
                  :class="{ active: (m.chartType || m.charts[0].type) === c.type }"
                  @click="m.chartType = c.type"
                >
                  {{ c.label }}
                </button>
              </div>
              <echart-block :option="activeChart(m)" />
            </div>
            <div v-if="m.citations && m.citations.length" class="cites">
              <span class="cites-label">
                <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
                  <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
                </svg>
                依据来源
              </span>
              <span v-for="c in prettyCitations(m.citations)" :key="c" class="cite">{{ c }}</span>
            </div>
            <!-- 无知识库引用、非图表洞察、非筛查流程的回答 = 通用 LLM 生成,加免责声明 -->
            <div
              v-else-if="
                m.role === 'assistant' && m.content && !m.isHighRisk && !m.chart &&
                m.intent !== 'screening'
              "
              class="disclaimer"
            >
              <span class="disclaimer-icon">
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <circle cx="12" cy="12" r="10" />
                  <path d="M12 16v-4M12 8h.01" />
                </svg>
              </span>
              <span class="disclaimer-text">
                <b>AI 生成内容</b>,基于通用营养学知识、未匹配知识库依据,仅供参考。涉及健康决策请咨询专业营养师或医生。
              </span>
            </div>
            <!-- 风险筛查:可点快捷选项(仅最新一条可点,点一下即作答) -->
            <div
              v-if="m.role === 'assistant' && m.quickReplies && m.quickReplies.length && i === messages.length - 1"
              class="quick-replies"
            >
              <span v-if="m.intent === 'insight'" class="qr-hint">
                <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <path d="M9 18h6M10 22h4M15.09 14c.18-.98.65-1.74 1.41-2.5A4.65 4.65 0 0 0 18 8 6 6 0 0 0 6 8c0 1 .23 2.23 1.5 3.5.76.76 1.23 1.52 1.41 2.5" />
                </svg>
                换个角度看,点一下试试:
              </span>
              <button
                v-for="q in m.quickReplies"
                :key="q"
                type="button"
                class="quick-reply"
                :disabled="loading"
                @click="send(q)"
              >
                {{ q }}
              </button>
            </div>
            <!-- AI 回复底部动作栏(Perplexity 风格):放在回复末尾,归属清晰、不与上方用户气泡混淆
                 图标全部 monochrome stroke SVG(Feather 风格),与分享弹窗的品牌色 SVG 形成
                 「主功能 monochrome / 渠道 brand-color」的视觉分层。 -->
            <div
              v-if="m.role === 'assistant' && m.content"
              class="msg-actions"
            >
              <button class="msg-action" title="复制回复" @click="copyMessage(m)">
                <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <rect x="9" y="9" width="11" height="11" rx="2"/>
                  <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
                </svg>
                <span class="msg-action-label">复制</span>
              </button>
              <button class="msg-action" title="生成可公开访问的分享链接" @click="shareMessage(m)">
                <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <circle cx="18" cy="5" r="3"/>
                  <circle cx="6" cy="12" r="3"/>
                  <circle cx="18" cy="19" r="3"/>
                  <line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/>
                  <line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/>
                </svg>
                <span class="msg-action-label">分享</span>
              </button>
              <!-- 重新生成只在最后一条 assistant 上提供,避免破坏后续对话上下文 -->
              <button
                v-if="i === messages.length - 1"
                class="msg-action"
                :disabled="loading"
                title="重新生成回复"
                @click="regenerate(m)"
              >
                <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <polyline points="23 4 23 10 17 10"/>
                  <polyline points="1 20 1 14 7 14"/>
                  <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
                </svg>
                <span class="msg-action-label">重新生成</span>
              </button>
              <span class="msg-actions-spacer" />
              <button
                class="msg-action rate"
                :class="{ active: m.rating === 'up' }"
                title="有用"
                @click="rate(m, 'up')"
              >
                <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/>
                </svg>
              </button>
              <button
                class="msg-action rate"
                :class="{ active: m.rating === 'down' }"
                title="待改进"
                @click="rate(m, 'down')"
              >
                <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3zm7-13h2.67A2.31 2.31 0 0 1 22 4v7a2.31 2.31 0 0 1-2.33 2H17"/>
                </svg>
              </button>
            </div>
          </div>
          <n-avatar v-if="m.role === 'user'" round class="avatar" :src="userAvatar" color="#e8eef0" />
        </div>
      </main>

      <div class="composer-area">
        <!-- 常驻能力快捷条:对话进行中也能随时唤起任一子 Agent(点击填入,可改) -->
        <div class="cap-bar">
          <span
            v-for="c in capabilities"
            :key="c.key"
            class="cap-pill"
            @click="fillPrompt(c.prompt)"
          >
            <cap-icon :name="c.key" :size="14" /><span>{{ c.name }}</span>
          </span>
        </div>
        <footer class="composer">
          <n-input
            v-model:value="input"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 4 }"
            placeholder="输入你的健康问题,Enter 发送(Shift+Enter 换行)"
            :disabled="loading"
            @keydown.enter.exact.prevent="send()"
          />
          <n-button type="primary" size="large" :loading="loading" :disabled="!input.trim()" @click="send()">
            发送
          </n-button>
        </footer>
      </div>
    </div>

    <!-- 头像选择器 -->
    <n-modal v-model:show="showAvatarPicker" preset="card" title="选择头像" style="width: 460px">
      <div class="avatar-grid">
        <div
          v-for="st in AVATAR_STYLES"
          :key="st"
          class="avatar-option"
          :class="{ active: st === auth.avatarStyle }"
          @click="pickAvatar(st)"
        >
          <img :src="avatarUrl(st)" :alt="st" />
        </div>
      </div>
    </n-modal>

    <!-- 分享对话框:链接 + 各社交渠道 intent URL -->
    <share-dialog
      v-model:show="shareOpen"
      :url="shareUrl"
      :title="shareTitle"
      :loading="shareLoading"
    />
  </div>
</template>

<style scoped>
.layout {
  height: 100vh;
  display: flex;
  background: radial-gradient(1200px 600px at 70% -10%, #eef6f4 0%, #f4f7f6 45%, #eef2f1 100%);
}

/* 细滚动条 */
.messages::-webkit-scrollbar,
.conv-list::-webkit-scrollbar {
  width: 8px;
}
.messages::-webkit-scrollbar-thumb {
  background: rgba(20, 64, 63, 0.16);
  border-radius: 8px;
}
.messages::-webkit-scrollbar-thumb:hover {
  background: rgba(20, 64, 63, 0.28);
}
.conv-list::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.16);
  border-radius: 8px;
}

/* ===== 侧边栏 ===== */
.sidebar {
  width: 264px;
  flex-shrink: 0;
  background: linear-gradient(185deg, #16413f 0%, #0e302f 100%);
  color: #e6f4f3;
  display: flex;
  flex-direction: column;
  padding: 18px 14px;
  box-shadow: 1px 0 0 rgba(255, 255, 255, 0.04), 6px 0 24px rgba(8, 30, 29, 0.18);
  overflow: hidden;
  transition: width 0.22s ease, padding 0.22s ease;
}
.sidebar.collapsed {
  width: 0;
  padding-left: 0;
  padding-right: 0;
}
.side-collapse {
  margin-left: auto;
  flex-shrink: 0;
  width: 26px;
  height: 26px;
  border-radius: 7px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.18);
  color: #cfe6e4;
  cursor: pointer;
  transition: background 0.15s;
}
.side-collapse:hover {
  background: rgba(255, 255, 255, 0.2);
}
.side-expand {
  position: absolute;
  left: 12px;
  top: 16px;
  z-index: 6;
  width: 32px;
  height: 32px;
  border-radius: 9px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #16413f;
  color: #e6f4f3;
  border: 1px solid rgba(255, 255, 255, 0.16);
  cursor: pointer;
  box-shadow: 0 4px 14px rgba(8, 30, 29, 0.25);
}
.side-expand:hover {
  background: #1d524f;
}
.side-brand {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 4px 6px 18px;
}
.side-brand .logo {
  font-size: 24px;
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(145deg, rgba(255, 255, 255, 0.14), rgba(255, 255, 255, 0.04));
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 12px;
}
.side-brand .name {
  font-size: 18px;
  font-weight: 800;
  color: #fff;
}
.side-brand .sub {
  font-size: 11px;
  opacity: 0.7;
}
.new-chat {
  margin-bottom: 16px;
}
.conv-list {
  flex: 1;
  overflow-y: auto;
}
.conv-list-title {
  font-size: 11px;
  opacity: 0.55;
  padding: 4px 8px;
  letter-spacing: 1px;
}
.conv-item {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 9px 11px;
  border-radius: 10px;
  cursor: pointer;
  font-size: 13px;
  color: #cfe6e4;
  transition: background 0.15s, color 0.15s;
}
.conv-item:hover {
  background: rgba(255, 255, 255, 0.07);
}
.conv-item.active {
  background: rgba(120, 220, 200, 0.16);
  color: #fff;
}
.conv-item.active::before {
  content: "";
  position: absolute;
  left: 0;
  top: 8px;
  bottom: 8px;
  width: 3px;
  border-radius: 3px;
  background: #6fe3c8;
}
.conv-title {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.conv-actions {
  display: flex;
  align-items: center;
  gap: 1px;
  flex-shrink: 0;
}
.conv-act {
  display: inline-flex;
  align-items: center;
  opacity: 0;
  padding: 2px 3px;
  cursor: pointer;
  color: #cfe6e4;
  transition: opacity 0.15s, color 0.15s;
}
.conv-item:hover .conv-act {
  opacity: 0.55;
}
.conv-act:hover {
  opacity: 1 !important;
}
/* 置顶态:常驻显示 + 品牌薄荷绿高亮(SVG 走 currentColor) */
.conv-pin.on {
  opacity: 1;
  color: #6fe3c8;
}
.conv-rename {
  flex: 1;
  min-width: 0;
  background: rgba(255, 255, 255, 0.12);
  border: 1px solid rgba(255, 255, 255, 0.35);
  border-radius: 6px;
  color: #fff;
  font-size: 13px;
  padding: 3px 7px;
  outline: none;
}
.conv-del {
  display: inline-flex;
  align-items: center;
  opacity: 0;
  padding: 2px 3px;
  color: #cfe6e4;
  cursor: pointer;
  transition: opacity 0.15s, color 0.15s;
}
.conv-item:hover .conv-del {
  opacity: 0.55;
}
.conv-del:hover {
  opacity: 1 !important;
  color: #ff9b9b;
}
.conv-item:hover .conv-del {
  opacity: 0.6;
}
.conv-del:hover {
  opacity: 1 !important;
}
.side-user {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 6px 4px;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
  margin-top: 8px;
}
.side-user .uid {
  flex: 1;
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
/* 退出按钮:深色侧栏上必须自带浅色描边,否则默认深色文字暗对暗看不见 */
.logout-btn {
  flex-shrink: 0;
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.28);
  color: #e6f4f3;
  font-size: 12px;
  padding: 4px 11px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}
.admin-btn {
  background: rgba(120, 220, 200, 0.18);
  border-color: rgba(120, 220, 200, 0.45);
  color: #d7f5ee;
}
.logout-btn:hover {
  background: rgba(255, 255, 255, 0.2);
  border-color: rgba(255, 255, 255, 0.5);
}

/* ===== 主对话 ===== */
.chat-main {
  position: relative;
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.side-brand-text {
  min-width: 0;
}
.messages {
  flex: 1;
  overflow-y: auto;
  /* 底部留白:给悬浮输入区让位,最后一条消息能滚到其上方 */
  padding: 28px 24px 132px;
  width: 100%;
  /* Claude / ChatGPT 式居中阅读列:固定舒适宽度,两侧对称留白;
     侧栏收起也只是对称居中,不会偏移、不会单侧空一大块。 */
  max-width: 1000px;
  margin: 0 auto;
}
.welcome {
  position: relative;
  text-align: center;
  margin-top: 4vh;
  color: #374151;
}
/* 欢迎区柔光背景:几团品牌 / Agent 主题色的柔和光晕,告别纯白单调 */
.welcome::before {
  content: "";
  position: absolute;
  left: 50%;
  top: -40px;
  width: 760px;
  height: 520px;
  transform: translateX(-50%);
  z-index: 0;
  pointer-events: none;
  background:
    radial-gradient(220px 200px at 22% 28%, rgba(20, 184, 166, 0.16), transparent 70%),
    radial-gradient(220px 200px at 80% 22%, rgba(245, 158, 11, 0.14), transparent 70%),
    radial-gradient(240px 220px at 30% 82%, rgba(34, 197, 94, 0.14), transparent 70%),
    radial-gradient(240px 220px at 82% 80%, rgba(124, 108, 240, 0.14), transparent 70%);
  filter: blur(8px);
}
.welcome > * {
  position: relative;
  z-index: 1;
}
.welcome-logo {
  font-size: 38px;
  line-height: 1;
  width: 76px;
  height: 76px;
  margin: 0 auto;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 24px;
  background: radial-gradient(circle at 50% 38%, #ffffff, #ecf7f4);
  box-shadow: 0 10px 26px rgba(47, 139, 137, 0.18), 0 0 0 1px rgba(47, 139, 137, 0.08) inset;
}
.welcome h2 {
  margin: 16px 0 4px;
  font-size: 22px;
  color: #14403f;
}
.welcome p {
  color: #6b7280;
  margin-bottom: 22px;
  font-size: 13.5px;
}
/* 欢迎页:4 个子 Agent 能力卡片(点击直接发起代表性提问) */
.cap-cards {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  max-width: 600px;
  margin: 0 auto;
}
.cap-card {
  position: relative;
  overflow: hidden;
  text-align: left;
  background: #fff;
  border: 1px solid #e9efee;
  border-radius: 18px;
  padding: 18px;
  cursor: pointer;
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
  box-shadow: 0 1px 2px rgba(16, 40, 39, 0.04);
}
/* 卡片右上角的主题色柔光晕染(随主题变量上色) */
.cap-card::after {
  content: "";
  position: absolute;
  top: -40px;
  right: -40px;
  width: 130px;
  height: 130px;
  border-radius: 50%;
  background: var(--accent-soft, rgba(47, 139, 137, 0.1));
  opacity: 0.7;
  transition: opacity 0.18s ease, transform 0.18s ease;
  pointer-events: none;
}
.cap-card:hover {
  border-color: var(--accent, #bfe3dd);
  box-shadow: 0 14px 32px var(--accent-soft, rgba(47, 139, 137, 0.18));
  transform: translateY(-3px);
}
.cap-card:hover::after {
  opacity: 1;
  transform: scale(1.15);
}
/* 各 Agent 专属主题色 */
.cap-card.theme-consult {
  --accent: #14b8a6;
  --accent-soft: rgba(20, 184, 166, 0.14);
}
.cap-card.theme-screening {
  --accent: #f59e0b;
  --accent-soft: rgba(245, 158, 11, 0.14);
}
.cap-card.theme-plan {
  --accent: #22c55e;
  --accent-soft: rgba(34, 197, 94, 0.14);
}
.cap-card.theme-insight {
  --accent: #7c6cf0;
  --accent-soft: rgba(124, 108, 240, 0.16);
}
.cap-art {
  position: relative;
  z-index: 1;
  line-height: 0;
  filter: drop-shadow(0 6px 12px var(--accent-soft, rgba(47, 139, 137, 0.18)));
}
.cap-name {
  position: relative;
  z-index: 1;
  margin-top: 13px;
  font-weight: 700;
  color: #14403f;
  font-size: 15px;
}
.cap-desc {
  position: relative;
  z-index: 1;
  margin-top: 3px;
  font-size: 12px;
  color: #6b7280;
}
.cap-try {
  position: relative;
  z-index: 1;
  margin-top: 10px;
  font-size: 12px;
  color: var(--accent, #2f8b89);
  background: var(--accent-soft, #eef6f5);
  border-radius: 8px;
  padding: 5px 9px;
}
.cap-try::before {
  content: "试试:";
  opacity: 0.7;
}

.row {
  display: flex;
  gap: 11px;
  margin-bottom: 14px;
  align-items: flex-start;
  animation: bubble-in 0.32s cubic-bezier(0.22, 1, 0.36, 1) both;
}
/* 一个「turn」 = 用户问 + AI 答;turn 之间(=下一条 user)再加大间距,
   视觉上明确分组,避免上一段答案的动作栏与下一段提问粘在一起。 */
.row + .row.user {
  margin-top: 28px;
}
@keyframes bubble-in {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
.row.user {
  flex-direction: row-reverse;
}
.avatar {
  flex-shrink: 0;
  box-shadow: 0 2px 6px rgba(16, 40, 39, 0.12);
}
.bubble {
  position: relative;
  max-width: 78%;
  padding: 14px 20px;
  border-radius: 16px;
  /* Perplexity 风格正文:更大字号 + 更舒展行高 */
  line-height: 1.78;
  font-size: 16px;
  white-space: pre-wrap;
  word-break: break-word;
}
/* AI 回复占满对话列宽度(填满布局,内容不再左缩一小块、右侧大留白);
   用户气泡仍靠右、限宽 78%。 */
.row:not(.user) .bubble {
  flex: 1 1 auto;
  max-width: 100%;
}
/* 复制按钮:hover 时出现在气泡右上角 */
.copy-btn {
  position: absolute;
  top: 6px;
  right: 8px;
  width: 22px;
  height: 22px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 12px;
  line-height: 1;
  opacity: 0;
  transition: opacity 0.15s, background 0.15s;
}
.bubble:hover .copy-btn {
  opacity: 1;
}
/* AI 回复底部动作栏:Perplexity 风格 —— 放在回复末尾,归属清晰 */
.msg-actions {
  display: flex;
  gap: 4px;
  margin-top: 14px;
  padding-top: 6px;
}
.msg-action {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  background: transparent;
  border: none;
  color: #6b8b88;
  font-size: 12.5px;
  padding: 5px 10px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.12s, color 0.12s;
}
.msg-action:hover {
  background: rgba(20, 64, 63, 0.06);
  color: #14403f;
}
.msg-action:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.msg-action-icon {
  font-size: 14px;
  line-height: 1;
}
/* 把 👍 👎 推到右端,与复制/分享/重新生成形成「左主功能 / 右反馈」的视觉分组 */
.msg-actions-spacer {
  flex: 1 1 auto;
}
.msg-action.rate {
  padding: 5px 8px;
}
.msg-action.rate.active {
  background: rgba(47, 139, 137, 0.12);
  color: #14403f;
}
.copy-btn.user {
  background: rgba(255, 255, 255, 0.22);
  color: #f0fffb;
}
.copy-btn.user:hover {
  background: rgba(255, 255, 255, 0.38);
}
/* Perplexity 风格:AI 回复去掉白卡片,纯文本直接铺在页面背景上 */
.bubble.assistant {
  background: transparent;
  color: #1f333a;
  letter-spacing: 0.1px;
  padding: 2px 4px;
  border: none;
  border-radius: 0;
  box-shadow: none;
}
.bubble.user {
  background: linear-gradient(135deg, #34948f 0%, #2a7d79 100%);
  color: #fff;
  border-top-right-radius: 5px;
  white-space: normal;
  box-shadow: 0 6px 18px rgba(42, 125, 121, 0.28);
}
/* 「营养师思路」过程轨迹 —— Hanako 式 `› ...` 灰斜体,把 LangGraph
   多 agent 调度链以最低视觉权重呈现:用户读得到、又不抢答案焦点。 */
.process-trace {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 12px;
  font-size: 12.5px;
  color: #8a9b98;
  font-style: italic;
  font-family: ui-monospace, "SF Mono", "JetBrains Mono", Consolas, monospace;
  line-height: 1.6;
  letter-spacing: 0.1px;
}
.pt-arrow {
  color: #b9c5c3;
  font-style: normal;
  font-weight: 700;
}
.pt-step b {
  color: #2f8b89;
  font-weight: 600;
  font-style: normal;
}
.pt-step.pt-risk b {
  color: #c1592a;
}
.pt-sep {
  color: #c8d2d0;
  font-style: normal;
}
.pt-tag {
  font-style: normal;
  font-size: 11px;
  padding: 1px 8px;
  border-radius: 999px;
  font-family: inherit;
}
.pt-tag-risk {
  background: #fbeee5;
  color: #c1592a;
}

.bubble .meta {
  display: flex;
  gap: 6px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}
.thinking {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #6b7280;
}

/* ===== Markdown 紧凑排版 ===== */
.markdown {
  white-space: normal;
}
.markdown :deep(h1),
.markdown :deep(h2),
.markdown :deep(h3),
.markdown :deep(h4) {
  font-size: 16.5px;
  font-weight: 700;
  /* 每天之间留更大间距,分组更清晰(Perplexity 那种段落呼吸感) */
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
.markdown :deep(li > p) {
  margin: 0;
}
.markdown :deep(strong) {
  color: #14403f;
  font-weight: 700;
}
.markdown :deep(code) {
  background: #eef2f2;
  padding: 1px 6px;
  border-radius: 5px;
  font-size: 13px;
  color: #b4531a;
}
.markdown :deep(pre) {
  background: #0f2e2d;
  color: #e6f4f3;
  padding: 12px 14px;
  border-radius: 10px;
  overflow-x: auto;
  margin: 8px 0;
}
.markdown :deep(pre code) {
  background: transparent;
  color: inherit;
  padding: 0;
}
.markdown :deep(table) {
  border-collapse: collapse;
  margin: 8px 0;
  font-size: 13px;
}
.markdown :deep(th),
.markdown :deep(td) {
  border: 1px solid #e5e7eb;
  padding: 6px 10px;
}
.markdown :deep(th) {
  background: #f0f7f6;
}
.markdown :deep(*:first-child) {
  margin-top: 0;
}
.markdown :deep(*:last-child) {
  margin-bottom: 0;
}

.bubble .cites {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px dashed #e5e7eb;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}
.cites-label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #9ca3af;
}
.cite {
  font-size: 12px;
  color: #2f8b89;
  background: #eef6f5;
  border: 1px solid #d6e9e7;
  border-radius: 6px;
  padding: 2px 8px;
}
.disclaimer {
  margin-top: 12px;
  display: flex;
  align-items: flex-start;
  gap: 7px;
  padding: 8px 11px;
  background: #fffaf0;
  border: 1px solid #ffe6b0;
  border-radius: 9px;
  font-size: 12px;
  line-height: 1.55;
  color: #946a00;
}
.disclaimer-icon {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  margin-top: 1px;
}
.disclaimer-text b {
  color: #7a5600;
  font-weight: 700;
}

/* 风险筛查快捷选项 / 数据洞察示例问题 */
.quick-replies {
  margin-top: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.qr-hint {
  width: 100%;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #9ca3af;
  margin-bottom: 2px;
}
.quick-reply {
  font-size: 13px;
  color: #2f8b89;
  background: #eef6f5;
  border: 1px solid #cfe6e4;
  border-radius: 999px;
  padding: 6px 14px;
  cursor: pointer;
  transition: all 0.12s;
}
.quick-reply:hover:not(:disabled) {
  background: #2f8b89;
  color: #fff;
  border-color: #2f8b89;
}
.quick-reply:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 数据洞察:图表切换 */
.chart-block {
  margin-top: 10px;
}
.chart-tabs {
  display: flex;
  gap: 6px;
  margin-bottom: 6px;
}
.chart-tab {
  font-size: 12.5px;
  color: #5a6b69;
  background: #f2f6f5;
  border: 1px solid #e3edeb;
  border-radius: 8px;
  padding: 4px 12px;
  cursor: pointer;
  transition: all 0.12s;
}
.chart-tab:hover {
  border-color: #2f8b89;
  color: #2f8b89;
}
.chart-tab.active {
  background: #2f8b89;
  border-color: #2f8b89;
  color: #fff;
}

/* 头像可点 + 选择器网格 */
.clickable-avatar {
  cursor: pointer;
  transition: transform 0.12s;
}
.clickable-avatar:hover {
  transform: scale(1.08);
}
.avatar-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}
.avatar-option {
  border: 2px solid transparent;
  border-radius: 12px;
  padding: 4px;
  cursor: pointer;
  transition: all 0.12s;
  background: #f3f5f7;
}
.avatar-option:hover {
  border-color: #9ad;
}
.avatar-option.active {
  border-color: #2f8b89;
  background: #eef6f5;
}
.avatar-option img {
  width: 100%;
  display: block;
  border-radius: 8px;
}

/* 底部悬空:绝对定位浮在消息之上,顶部渐隐 —— 内容可从其下方滚过 */
.composer-area {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  padding: 30px 0 16px;
  background: linear-gradient(
    to top,
    #eef3f2 42%,
    rgba(238, 243, 242, 0.82) 68%,
    rgba(238, 243, 242, 0)
  );
  pointer-events: none; /* 透明渐隐区可穿透,滚动作用到下方消息 */
}
.cap-bar,
.composer {
  pointer-events: auto; /* 快捷条与输入框正常可点 */
}
/* 输入框做成悬浮卡片:白底 + 圆角 + 投影;聚焦时青绿光晕 */
.composer :deep(.n-input) {
  border-radius: 16px;
  background: #fff;
  box-shadow: 0 8px 26px rgba(16, 40, 39, 0.1);
}
.composer :deep(.n-input.n-input--focus) {
  box-shadow: 0 8px 26px rgba(16, 40, 39, 0.12), 0 0 0 3px rgba(47, 139, 137, 0.16);
}
.cap-bar {
  max-width: 1000px;
  margin: 0 auto;
  padding: 10px 24px 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.cap-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12.5px;
  color: #2f8b89;
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid #d6e9e7;
  border-radius: 999px;
  padding: 5px 13px;
  cursor: pointer;
  transition: all 0.12s;
  user-select: none;
  box-shadow: 0 2px 8px rgba(16, 40, 39, 0.06);
}
.cap-pill svg {
  flex-shrink: 0;
}
.cap-pill:hover {
  background: #2f8b89;
  color: #fff;
  border-color: #2f8b89;
}
.composer {
  padding: 0 24px;
  display: flex;
  gap: 12px;
  align-items: flex-end;
  width: 100%;
  max-width: 1000px;
  margin: 0 auto;
}
</style>
