<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import { useMessage, NCard, NForm, NFormItem, NInput, NButton } from "naive-ui";
import { useAuthStore } from "@/stores/auth";

const router = useRouter();
const message = useMessage();
const auth = useAuthStore();

const username = ref("demo");
const password = ref("nutricore2024");
const loading = ref(false);

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
