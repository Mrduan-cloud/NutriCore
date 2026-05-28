import { defineStore } from "pinia";
import { ref } from "vue";

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  intent?: string | null;
  isHighRisk?: boolean;
  citations?: string[];
  usedTools?: string[];
}

export interface Conversation {
  id: string;
  title: string;
  messages: ChatMessage[];
  createdAt: number;
}

const KEY = "nutricore_conversations";

function load(): Conversation[] {
  try {
    return JSON.parse(localStorage.getItem(KEY) || "[]");
  } catch {
    return [];
  }
}

function persist(list: Conversation[]) {
  localStorage.setItem(KEY, JSON.stringify(list));
}

export const useConversationStore = defineStore("conversations", () => {
  const list = ref<Conversation[]>(load());
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
    persist(list.value);
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
    persist(list.value);
  }

  function save() {
    // 标题用第一条用户消息(截断)
    const conv = list.value.find((c) => c.id === activeId.value);
    if (conv) {
      const firstUser = conv.messages.find((m) => m.role === "user");
      if (firstUser) conv.title = firstUser.content.slice(0, 18);
    }
    persist(list.value);
  }

  return { list, activeId, newConversation, active, select, remove, save };
});
