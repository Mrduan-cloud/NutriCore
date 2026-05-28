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

        <div class="quick-users">
          <span class="qu-label">快速选择</span>
          <button
            v-for="u in users"
            :key="u"
            type="button"
            class="qu-chip"
            :class="{ active: u === username }"
            @click="pickUser(u)"
          >
            {{ u }}
          </button>
          <button type="button" class="qu-add" @click="showAdd = true">＋ 添加用户</button>
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
      <p class="hint">演示账号:demo / nutricore2024</p>
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
.quick-users {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin: 2px 0 18px;
}
.qu-label {
  font-size: 12px;
  color: #9ca3af;
}
.qu-chip {
  font-size: 13px;
  color: #2f8b89;
  background: #eef6f5;
  border: 1px solid #d6e9e7;
  border-radius: 999px;
  padding: 3px 12px;
  cursor: pointer;
  transition: all 0.12s;
}
.qu-chip:hover {
  border-color: #2f8b89;
}
.qu-chip.active {
  background: #2f8b89;
  color: #fff;
  border-color: #2f8b89;
}
.qu-add {
  font-size: 13px;
  color: #6b7280;
  background: #fff;
  border: 1px dashed #cbd5e1;
  border-radius: 999px;
  padding: 3px 12px;
  cursor: pointer;
  transition: all 0.12s;
}
.qu-add:hover {
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
