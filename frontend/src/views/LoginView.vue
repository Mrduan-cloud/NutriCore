<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { useMessage, NCard, NForm, NFormItem, NInput, NButton, NModal } from "naive-ui";
import axios from "axios";
import { useAuthStore } from "@/stores/auth";

const router = useRouter();
const message = useMessage();
const auth = useAuthStore();

const username = ref("demo");
const password = ref("nutricore2024");
const loading = ref(false);

// 用户列表(供快速选择)+ 添加用户
const users = ref<string[]>(["demo", "xinxin"]);
const showAdd = ref(false);
const newUser = ref("");
const adding = ref(false);

// 已知演示人设的画像速记(只为登录页一眼可读,新建用户无标签)
const PERSONA_HINTS: Record<string, string> = {
  demo: "男 · 高血压 · 控盐",
  xinxin: "女 · 素食 · 减脂",
};
function personaHint(u: string): string {
  return PERSONA_HINTS[u] || "";
}

async function fetchUsers() {
  try {
    const { data } = await axios.get("/api/auth/users");
    // demo / xinxin 固定置顶,其余去重补上
    users.value = [...new Set(["demo", "xinxin", ...(data.users || [])])];
  } catch {
    users.value = ["demo", "xinxin"];
  }
}

onMounted(fetchUsers);

function pickUser(u: string) {
  username.value = u;
}

async function onAddUser() {
  const name = newUser.value.trim();
  if (!name) {
    message.warning("请输入用户名");
    return;
  }
  adding.value = true;
  try {
    await axios.post("/api/auth/register", { username: name, password: password.value });
    message.success(`用户「${name}」已创建`);
    await fetchUsers();
    username.value = name;
    newUser.value = "";
    showAdd.value = false;
  } catch (e: any) {
    message.error(e?.response?.data?.detail || "创建失败,请重试");
  } finally {
    adding.value = false;
  }
}

async function onLogin() {
  if (!username.value || !password.value) {
    message.warning("请输入用户名和口令");
    return;
  }
  loading.value = true;
  try {
    await auth.login(username.value, password.value);
    message.success("登录成功");
    router.push("/chat");
  } catch (e: any) {
    message.error(e?.response?.data?.detail || "登录失败,请重试");
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="login-wrap">
    <div class="brand">
      <div class="logo">🥗</div>
      <h1>NutriCore</h1>
      <p>AI 营养健康多智能体协同平台</p>
    </div>

    <n-card class="login-card" :bordered="false">
      <h2 class="title">登录</h2>
      <n-form @submit.prevent="onLogin">
        <n-form-item label="用户名">
          <n-input v-model:value="username" placeholder="demo-001" @keyup.enter="onLogin" />
        </n-form-item>
        <n-form-item label="口令">
          <n-input
            v-model:value="password"
            type="password"
            show-password-on="click"
            placeholder="demo123"
            @keyup.enter="onLogin"
          />
        </n-form-item>

        <div class="personas">
          <span class="p-label">演示人设 · 点选快速体验</span>
          <button
            v-for="u in users"
            :key="u"
            type="button"
            class="persona"
            :class="{ active: u === username }"
            @click="pickUser(u)"
          >
            <span class="p-name">{{ u }}</span>
            <span v-if="personaHint(u)" class="p-tag">{{ personaHint(u) }}</span>
          </button>
          <button type="button" class="persona add" @click="showAdd = true">＋ 添加</button>
        </div>

        <n-button
          type="primary"
          block
          size="large"
          :loading="loading"
          @click="onLogin"
        >
          登 录
        </n-button>
      </n-form>
      <p class="hint">演示账号:demo / xinxin · 口令 nutricore2024</p>
    </n-card>

    <!-- 添加用户 -->
    <n-modal v-model:show="showAdd" preset="card" title="添加用户" style="width: 360px">
      <n-input
        v-model:value="newUser"
        placeholder="字母 / 数字 / 下划线,1-32 位"
        :disabled="adding"
        @keyup.enter="onAddUser"
      />
      <p class="add-hint">将以当前口令创建(默认 nutricore2024)</p>
      <template #footer>
        <div class="add-actions">
          <n-button :disabled="adding" @click="showAdd = false">取消</n-button>
          <n-button type="primary" :loading="adding" @click="onAddUser">创建并选择</n-button>
        </div>
      </template>
    </n-modal>

    <p class="footer">Powered by LangGraph · DeepSeek · RAG · 4-Agent 协同</p>
  </div>
</template>

<style scoped>
.login-wrap {
  min-height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #2f8b89 0%, #1f5f5e 60%, #15403f 100%);
  padding: 24px;
}
.brand {
  text-align: center;
  color: #fff;
  margin-bottom: 28px;
}
.brand .logo {
  font-size: 56px;
}
.brand h1 {
  font-size: 38px;
  font-weight: 800;
  letter-spacing: 1px;
  margin: 6px 0;
}
.brand p {
  opacity: 0.9;
  font-size: 15px;
}
.login-card {
  width: 380px;
  max-width: 90vw;
  border-radius: 18px;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.25);
}
.title {
  text-align: center;
  margin-bottom: 18px;
  color: #1f2937;
}
.personas {
  display: flex;
  flex-wrap: wrap;
  align-items: stretch;
  gap: 8px;
  margin: 2px 0 18px;
}
.p-label {
  width: 100%;
  font-size: 12px;
  color: #9ca3af;
  margin-bottom: 2px;
}
.persona {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  background: #f4f8f7;
  border: 1px solid #dcebe9;
  border-radius: 10px;
  padding: 7px 12px;
  cursor: pointer;
  transition: all 0.12s;
  min-width: 76px;
}
.persona:hover {
  border-color: #2f8b89;
}
.persona.active {
  background: #2f8b89;
  border-color: #2f8b89;
}
.persona.active .p-name,
.persona.active .p-tag {
  color: #fff;
}
.p-name {
  font-size: 14px;
  font-weight: 600;
  color: #14403f;
}
.p-tag {
  font-size: 11px;
  color: #6b8b88;
}
.persona.add {
  justify-content: center;
  align-items: center;
  color: #6b7280;
  background: #fff;
  border-style: dashed;
  border-color: #cbd5e1;
  font-size: 13px;
}
.persona.add:hover {
  border-color: #2f8b89;
  color: #2f8b89;
}
.add-hint {
  font-size: 12px;
  color: #9ca3af;
  margin-top: 8px;
}
.add-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.hint {
  text-align: center;
  color: #9ca3af;
  font-size: 13px;
  margin-top: 14px;
}
.footer {
  margin-top: 24px;
  color: rgba(255, 255, 255, 0.75);
  font-size: 13px;
}
</style>
