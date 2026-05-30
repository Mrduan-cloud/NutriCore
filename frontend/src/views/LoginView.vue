<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { useMessage, NCard, NForm, NFormItem, NInput, NButton, NModal } from "naive-ui";
import axios from "axios";
import { useAuthStore } from "@/stores/auth";

const router = useRouter();
const message = useMessage();
const auth = useAuthStore();

const username = ref("李哲");
const password = ref("nutricore2024");
const loading = ref(false);

// 演示人设(仅 is_demo 账号,经 /demo-accounts 暴露,不泄露真实用户名)
const demoUsers = ref<string[]>(["李哲", "林悦"]);
// 演示口令(供快速体验一键填充)
const DEMO_PASSWORD = "nutricore2024";

const PERSONA_HINTS: Record<string, string> = {
  "李哲": "男 · 高血压 · 控盐",
  "林悦": "女 · 素食 · 减脂",
};
function personaHint(u: string): string {
  return PERSONA_HINTS[u] || "演示账号";
}

// 注册
const showReg = ref(false);
const regUser = ref("");
const regPwd = ref("");
const regPwd2 = ref("");
const registering = ref(false);

async function fetchDemoUsers() {
  try {
    const { data } = await axios.get("/api/auth/demo-accounts");
    if (Array.isArray(data.users) && data.users.length) demoUsers.value = data.users;
  } catch {
    /* 用默认演示人设兜底 */
  }
}
onMounted(fetchDemoUsers);

// 点选演示人设:同时填入用户名 + 演示口令,一键可登
function pickDemo(u: string) {
  username.value = u;
  password.value = DEMO_PASSWORD;
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
    router.push(auth.isAdmin ? "/admin" : "/chat");
  } catch (e: any) {
    message.error(e?.response?.data?.detail || "登录失败,请重试");
  } finally {
    loading.value = false;
  }
}

async function onRegister() {
  const u = regUser.value.trim();
  if (!u) return message.warning("请输入用户名");
  if (regPwd.value.length < 6) return message.warning("口令至少 6 位");
  if (regPwd.value !== regPwd2.value) return message.warning("两次口令不一致");
  registering.value = true;
  try {
    await auth.register(u, regPwd.value);
    message.success(`欢迎,${u}！`);
    showReg.value = false;
    router.push("/chat");
  } catch (e: any) {
    message.error(e?.response?.data?.detail || "注册失败,请重试");
  } finally {
    registering.value = false;
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
          <n-input v-model:value="username" placeholder="你的用户名" @keyup.enter="onLogin" />
        </n-form-item>
        <n-form-item label="口令">
          <n-input
            v-model:value="password"
            type="password"
            show-password-on="click"
            placeholder="你的口令"
            @keyup.enter="onLogin"
          />
        </n-form-item>

        <div class="personas">
          <span class="p-label">演示人设 · 一键填充体验</span>
          <button
            v-for="u in demoUsers"
            :key="u"
            type="button"
            class="persona"
            :class="{ active: u === username }"
            @click="pickDemo(u)"
          >
            <span class="p-name">{{ u }}</span>
            <span class="p-tag">{{ personaHint(u) }}</span>
          </button>
        </div>

        <n-button type="primary" block size="large" :loading="loading" @click="onLogin">
          登 录
        </n-button>
        <div class="reg-row">
          还没有账号?<a class="reg-link" @click="showReg = true">注册新用户</a>
        </div>
      </n-form>
      <p class="hint">演示账号:李哲 / 林悦 · 口令 nutricore2024</p>
      <p class="hint admin-hint">管理后台:admin · 口令 nutricore-admin-2024</p>
    </n-card>

    <!-- 注册 -->
    <n-modal v-model:show="showReg" preset="card" title="注册新用户" style="width: 380px">
      <n-form @submit.prevent="onRegister">
        <n-form-item label="用户名">
          <n-input v-model:value="regUser" placeholder="中文 / 字母 / 数字 / 下划线,1-32 位" />
        </n-form-item>
        <n-form-item label="设置口令">
          <n-input
            v-model:value="regPwd"
            type="password"
            show-password-on="click"
            placeholder="至少 6 位"
          />
        </n-form-item>
        <n-form-item label="确认口令">
          <n-input
            v-model:value="regPwd2"
            type="password"
            show-password-on="click"
            placeholder="再输入一次"
            @keyup.enter="onRegister"
          />
        </n-form-item>
      </n-form>
      <template #footer>
        <div class="reg-actions">
          <n-button :disabled="registering" @click="showReg = false">取消</n-button>
          <n-button type="primary" :loading="registering" @click="onRegister">
            注册并登录
          </n-button>
        </div>
      </template>
    </n-modal>

    <p class="footer">Powered by LangGraph · DeepSeek · RAG · 4-Agent 协同</p>
  </div>
</template>

<style scoped>
.login-wrap {
  position: relative;
  min-height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background:
    radial-gradient(900px 520px at 18% 12%, rgba(111, 227, 200, 0.28) 0%, transparent 55%),
    radial-gradient(800px 600px at 88% 88%, rgba(28, 84, 82, 0.55) 0%, transparent 60%),
    linear-gradient(140deg, #2f8b89 0%, #1f5f5e 58%, #11302f 100%);
  padding: 24px;
  overflow: hidden;
}
.brand {
  position: relative;
  text-align: center;
  color: #fff;
  margin-bottom: 28px;
  animation: rise 0.5s cubic-bezier(0.22, 1, 0.36, 1) both;
}
.brand .logo {
  font-size: 40px;
  width: 78px;
  height: 78px;
  margin: 0 auto;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(150deg, rgba(255, 255, 255, 0.22), rgba(255, 255, 255, 0.06));
  border: 1px solid rgba(255, 255, 255, 0.28);
  border-radius: 22px;
  box-shadow: 0 12px 30px rgba(8, 30, 29, 0.35);
  backdrop-filter: blur(4px);
}
.brand h1 {
  font-size: 38px;
  font-weight: 800;
  letter-spacing: 1px;
  margin: 14px 0 6px;
}
.brand p {
  opacity: 0.92;
  font-size: 15px;
}
.login-card {
  position: relative;
  width: 384px;
  max-width: 90vw;
  border-radius: 20px;
  box-shadow: 0 24px 60px rgba(6, 24, 23, 0.35), 0 2px 0 rgba(255, 255, 255, 0.5) inset;
  animation: rise 0.55s cubic-bezier(0.22, 1, 0.36, 1) 0.06s both;
}
@keyframes rise {
  from {
    opacity: 0;
    transform: translateY(14px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
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
.reg-row {
  text-align: center;
  margin-top: 14px;
  font-size: 13px;
  color: #6b7280;
}
.reg-link {
  color: #2f8b89;
  font-weight: 600;
  cursor: pointer;
}
.reg-link:hover {
  text-decoration: underline;
}
.reg-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.hint {
  text-align: center;
  color: #9ca3af;
  font-size: 13px;
  margin-top: 12px;
}
.admin-hint {
  margin-top: 2px;
  color: #b8c0c0;
  font-size: 12px;
}
.footer {
  margin-top: 24px;
  color: rgba(255, 255, 255, 0.75);
  font-size: 13px;
}
</style>
