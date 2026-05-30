import { defineStore } from "pinia";
import { ref } from "vue";
import { useAuthStore } from "@/stores/auth";

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  intent?: string | null;
  isHighRisk?: boolean;
  citations?: string[];
  usedTools?: string[];
  // 数据洞察:后端随 done 事件下发的 ECharts 配置(持久化后可回看重绘)
  chart?: Record<string, any> | null;
  // 多套可切换图 [{type,label,option}] + 当前选中类型
  charts?: Array<{ type: string; label: string; option: Record<string, any> }>;
  chartType?: string;
  // 风险筛查:可点快捷选项(点一下即作答),仅在最新一条上展示
  quickReplies?: string[];
}

export interface Conversation {
  id: string;
  title: string;
  messages: ChatMessage[];
  createdAt: number;
  pinned?: boolean;
}

// 会话历史按用户隔离:localStorage key 带 user_id 后缀,切换账号互不串扰。
const PREFIX = "nutricore_conversations_";
function keyFor(uid: string): string {
  return PREFIX + (uid || "anon");
}

function load(uid: string): Conversation[] {
  try {
    return JSON.parse(localStorage.getItem(keyFor(uid)) || "[]");
  } catch {
    return [];
  }
}

function persist(uid: string, list: Conversation[]) {
  localStorage.setItem(keyFor(uid), JSON.stringify(list));
}

export const useConversationStore = defineStore("conversations", () => {
  const auth = useAuthStore();
  const list = ref<Conversation[]>(load(auth.userId));
  const activeId = ref<string>("");

  function newConversation(): Conversation {
    const conv: Conversation = {
      id: `c_${Date.now()}`,
      title: "新对话",
      messages: [],
      createdAt: Date.now(),
    };
    list.value.unshift(conv);
    activeId.value = conv.id;
    persist(auth.userId, list.value);
    return conv;
  }

  function active(): Conversation {
    let conv = list.value.find((c) => c.id === activeId.value);
    if (!conv) conv = list.value[0] || newConversation();
    activeId.value = conv.id;
    return conv;
  }

  function select(id: string) {
    activeId.value = id;
  }

  function remove(id: string) {
    list.value = list.value.filter((c) => c.id !== id);
    if (activeId.value === id) activeId.value = list.value[0]?.id || "";
    persist(auth.userId, list.value);
  }

  function save() {
    // 标题用第一条用户消息(截断)
    const conv = list.value.find((c) => c.id === activeId.value);
    if (conv) {
      const firstUser = conv.messages.find((m) => m.role === "user");
      if (firstUser) conv.title = firstUser.content.slice(0, 18);
    }
    persist(auth.userId, list.value);
  }

  // 置顶 / 取消置顶
  function togglePin(id: string) {
    const c = list.value.find((x) => x.id === id);
    if (c) {
      c.pinned = !c.pinned;
      persist(auth.userId, list.value);
    }
  }

  // 渲染顺序:置顶在前,各组内保持原顺序(最近的在上)
  function ordered(): Conversation[] {
    return [...list.value].sort((a, b) => (b.pinned ? 1 : 0) - (a.pinned ? 1 : 0));
  }

  // 切换账号后重新载入当前用户的会话(在进入聊天页时调用)
  function reload() {
    list.value = load(auth.userId);
    activeId.value = list.value[0]?.id || "";
  }

  return {
    list, activeId, newConversation, active, select, remove, save, reload,
    togglePin, ordered,
  };
});
