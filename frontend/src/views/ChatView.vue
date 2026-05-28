<script setup lang="ts">
import { ref, computed, nextTick, onMounted } from "vue";
import { useRouter } from "vue-router";
import {
  useMessage,
  NButton,
  NInput,
  NTag,
  NSpin,
  NAvatar,
  NPopconfirm,
  NModal,
} from "naive-ui";
import MarkdownIt from "markdown-it";
import { useAuthStore } from "@/stores/auth";
import { useConversationStore, type ChatMessage } from "@/stores/conversations";

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

// 当前会话的消息(响应式指向 store 里 active 会话)
const messages = computed<ChatMessage[]>(() => convStore.active().messages);

const examples = [
  "低 GI 的主食有哪些推荐?",
  "我想减脂,日常三餐怎么搭配?",
  "健身增肌期蛋白质怎么补充?",
  "帮我生成一份七天减脂食谱",
];

const intentLabel: Record<string, string> = {
  consult: "营养咨询",
  screening: "风险筛查",
  plan: "膳食方案",
  insight: "数据洞察",
  risk_alert: "健康提示",
};

onMounted(() => {
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
  conv.messages.push({ role: "user", content });
  // 占位 assistant 消息,流式往里填;取回 reactive 代理引用
  conv.messages.push({ role: "assistant", content: "", citations: [], usedTools: [] });
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
      body: JSON.stringify({ message: content }),
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

function onLogout() {
  auth.logout();
  router.push("/login");
}
</script>

<template>
  <div class="layout">
    <!-- ===== 左侧边栏 ===== -->
    <aside class="sidebar">
      <div class="side-brand">
        <span class="logo">🥗</span>
        <div>
          <div class="name">NutriCore</div>
          <div class="sub">AI 营养师</div>
        </div>
      </div>

      <n-button class="new-chat" type="primary" block @click="onNewChat">
        ＋ 新对话
      </n-button>

      <div class="conv-list">
        <div class="conv-list-title">历史对话</div>
        <div
          v-for="c in convStore.list"
          :key="c.id"
          class="conv-item"
          :class="{ active: c.id === convStore.activeId }"
          @click="onSelectConv(c.id)"
        >
          <span class="conv-title">{{ c.title || "新对话" }}</span>
          <n-popconfirm @positive-click="onDeleteConv(c.id)">
            <template #trigger>
              <span class="conv-del" @click.stop>✕</span>
            </template>
            删除这条对话?
          </n-popconfirm>
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
        <n-popconfirm @positive-click="onLogout">
          <template #trigger>
            <n-button size="tiny" quaternary>退出</n-button>
          </template>
          确定退出登录?
        </n-popconfirm>
      </div>
    </aside>

    <!-- ===== 右侧主对话 ===== -->
    <div class="chat-main">
      <main ref="listRef" class="messages">
        <!-- 欢迎 -->
        <div v-if="messages.length === 0" class="welcome">
          <div class="welcome-logo">🥗</div>
          <h2>你好,我是 NutriCore AI 营养师</h2>
          <p>我可以帮你做营养咨询、风险筛查、膳食方案和健康数据洞察。试试:</p>
          <div class="examples">
            <div v-for="ex in examples" :key="ex" class="example-chip" @click="send(ex)">
              {{ ex }}
            </div>
          </div>
        </div>

        <!-- 气泡 -->
        <div v-for="(m, i) in messages" :key="i" class="row" :class="m.role">
          <n-avatar v-if="m.role === 'assistant'" round class="avatar" color="#2F8B89">
            🥗
          </n-avatar>
          <div class="bubble" :class="m.role">
            <div v-if="m.role === 'assistant' && m.intent" class="meta">
              <n-tag size="small" :type="m.isHighRisk ? 'warning' : 'success'" :bordered="false">
                {{ intentLabel[m.intent] || m.intent }}
              </n-tag>
              <n-tag v-for="t in m.usedTools" :key="t" size="small" type="info" :bordered="false">
                🔧 {{ t }}
              </n-tag>
            </div>
            <template v-if="m.role === 'assistant'">
              <div v-if="!m.content" class="thinking">
                <n-spin size="small" /> <span>营养师思考中…</span>
              </div>
              <div v-else class="text markdown" v-html="renderMarkdown(m.content)" />
            </template>
            <div v-else class="text">{{ m.content }}</div>
            <div v-if="m.citations && m.citations.length" class="cites">
              <span class="cites-label">📚 依据来源</span>
              <span v-for="c in prettyCitations(m.citations)" :key="c" class="cite">{{ c }}</span>
            </div>
            <!-- 无知识库引用的回答 = 通用 LLM 生成,加免责声明 -->
            <div
              v-else-if="m.role === 'assistant' && m.content && !m.isHighRisk"
              class="disclaimer"
            >
              <span class="disclaimer-icon">💡</span>
              <span class="disclaimer-text">
                <b>AI 生成内容</b>,基于通用营养学知识、未匹配知识库依据,仅供参考。涉及健康决策请咨询专业营养师或医生。
              </span>
            </div>
          </div>
          <n-avatar v-if="m.role === 'user'" round class="avatar" :src="userAvatar" color="#e8eef0" />
        </div>
      </main>

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
  </div>
</template>

<style scoped>
.layout {
  height: 100vh;
  display: flex;
  background: #f3f5f7;
}

/* ===== 侧边栏 ===== */
.sidebar {
  width: 260px;
  flex-shrink: 0;
  background: #14403f;
  color: #e6f4f3;
  display: flex;
  flex-direction: column;
  padding: 16px 12px;
}
.side-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 6px 16px;
}
.side-brand .logo {
  font-size: 26px;
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
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 9px 10px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  color: #cfe6e4;
  transition: background 0.15s;
}
.conv-item:hover {
  background: rgba(255, 255, 255, 0.07);
}
.conv-item.active {
  background: rgba(255, 255, 255, 0.13);
  color: #fff;
}
.conv-title {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.conv-del {
  opacity: 0;
  font-size: 12px;
  padding: 0 4px;
  color: #cfe6e4;
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

/* ===== 主对话 ===== */
.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.messages {
  flex: 1;
  overflow-y: auto;
  padding: 28px 24px;
  width: 100%;
  max-width: 820px;
  margin: 0 auto;
}
.welcome {
  text-align: center;
  margin-top: 10vh;
  color: #374151;
}
.welcome-logo {
  font-size: 60px;
}
.welcome h2 {
  margin: 12px 0 8px;
}
.welcome p {
  color: #6b7280;
  margin-bottom: 20px;
}
.examples {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  justify-content: center;
}
.example-chip {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 11px 16px;
  cursor: pointer;
  transition: all 0.15s;
  color: #2f8b89;
  font-size: 14px;
}
.example-chip:hover {
  border-color: #2f8b89;
  box-shadow: 0 4px 12px rgba(47, 139, 137, 0.15);
  transform: translateY(-1px);
}

.row {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
  align-items: flex-start;
}
.row.user {
  flex-direction: row-reverse;
}
.avatar {
  flex-shrink: 0;
}
.bubble {
  max-width: 78%;
  padding: 11px 15px;
  border-radius: 14px;
  line-height: 1.7;
  font-size: 15px;
  white-space: pre-wrap;
  word-break: break-word;
}
.bubble.assistant {
  background: #fff;
  color: #1f2937;
  border-top-left-radius: 4px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
}
.bubble.user {
  background: #2f8b89;
  color: #fff;
  border-top-right-radius: 4px;
  white-space: normal;
}
.bubble .meta {
  display: flex;
  gap: 6px;
  margin-bottom: 8px;
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
  font-size: 15px;
  font-weight: 700;
  margin: 10px 0 4px;
  color: #14403f;
}
.markdown :deep(p) {
  margin: 4px 0;
}
.markdown :deep(ul),
.markdown :deep(ol) {
  margin: 4px 0;
  padding-left: 20px;
}
.markdown :deep(li) {
  margin: 0;
  line-height: 1.55;
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
  font-size: 13px;
  line-height: 1.5;
}
.disclaimer-text b {
  color: #7a5600;
  font-weight: 700;
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

.composer {
  flex-shrink: 0;
  background: #fff;
  border-top: 1px solid #e5e7eb;
  padding: 14px 24px;
  display: flex;
  gap: 12px;
  align-items: flex-end;
  width: 100%;
  max-width: 820px;
  margin: 0 auto;
}
</style>
