<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import {
  useMessage,
  NButton,
  NTag,
  NModal,
  NInput,
  NSelect,
  NPopconfirm,
  NSpin,
} from "naive-ui";
import client from "@/api/client";
import { useAuthStore } from "@/stores/auth";

const router = useRouter();
const message = useMessage();
const auth = useAuthStore();

interface AdminUser {
  username: string;
  role: string;
  is_demo: boolean;
  is_active: boolean;
  locked: boolean;
  failed_attempts: number;
  last_login_at: string | null;
  created_at: string | null;
}

const users = ref<AdminUser[]>([]);
const loading = ref(false);

async function load() {
  loading.value = true;
  try {
    const { data } = await client.get("/api/admin/users");
    users.value = data.users || [];
  } catch (e: any) {
    message.error(e?.response?.data?.detail || "加载失败");
  } finally {
    loading.value = false;
  }
}
onMounted(load);

function fmt(ts: string | null): string {
  if (!ts) return "—";
  return new Date(ts).toLocaleString("zh-CN", { hour12: false });
}

// 新建用户
const showCreate = ref(false);
const cUser = ref("");
const cPwd = ref("");
const cRole = ref("user");
const creating = ref(false);
const roleOptions = [
  { label: "普通用户", value: "user" },
  { label: "管理员", value: "admin" },
];

async function onCreate() {
  if (!cUser.value.trim()) return message.warning("请输入用户名");
  if (cPwd.value.length < 6) return message.warning("口令至少 6 位");
  creating.value = true;
  try {
    await client.post("/api/admin/users", {
      username: cUser.value.trim(),
      password: cPwd.value,
      role: cRole.value,
    });
    message.success("已创建");
    showCreate.value = false;
    cUser.value = "";
    cPwd.value = "";
    cRole.value = "user";
    await load();
  } catch (e: any) {
    message.error(e?.response?.data?.detail || "创建失败");
  } finally {
    creating.value = false;
  }
}

// 重置口令
const showReset = ref(false);
const resetTarget = ref("");
const resetPwd = ref("");
const resetting = ref(false);
function openReset(u: string) {
  resetTarget.value = u;
  resetPwd.value = "";
  showReset.value = true;
}
async function onReset() {
  if (resetPwd.value.length < 6) return message.warning("口令至少 6 位");
  resetting.value = true;
  try {
    await client.post(`/api/admin/users/${encodeURIComponent(resetTarget.value)}/reset-password`, {
      password: resetPwd.value,
    });
    message.success("口令已重置");
    showReset.value = false;
  } catch (e: any) {
    message.error(e?.response?.data?.detail || "重置失败");
  } finally {
    resetting.value = false;
  }
}

async function patchUser(u: AdminUser, body: Record<string, any>, ok: string) {
  try {
    await client.patch(`/api/admin/users/${encodeURIComponent(u.username)}`, body);
    message.success(ok);
    await load();
  } catch (e: any) {
    message.error(e?.response?.data?.detail || "操作失败");
  }
}

async function removeUser(u: AdminUser) {
  try {
    await client.delete(`/api/admin/users/${encodeURIComponent(u.username)}`);
    message.success("已删除");
    await load();
  } catch (e: any) {
    message.error(e?.response?.data?.detail || "删除失败");
  }
}

function logout() {
  auth.logout();
  router.push("/login");
}
</script>

<template>
  <div class="admin-wrap">
    <header class="bar">
      <div class="bar-left">
        <span class="logo">🥗</span>
        <h1>管理后台</h1>
        <span class="sub">账号与权限</span>
      </div>
      <div class="bar-right">
        <span class="me">管理员 · {{ auth.userId }}</span>
        <n-button quaternary size="small" @click="router.push('/chat')">进入对话</n-button>
        <n-button quaternary size="small" @click="logout">退出</n-button>
      </div>
    </header>

    <main class="body">
      <div class="toolbar">
        <div class="stat">共 <b>{{ users.length }}</b> 个账号</div>
        <div class="actions">
          <n-button size="small" @click="load">刷新</n-button>
          <n-button type="primary" size="small" @click="showCreate = true">＋ 新建用户</n-button>
        </div>
      </div>

      <n-spin :show="loading">
        <div class="table-card">
          <table class="tbl">
            <thead>
              <tr>
                <th>用户名</th>
                <th>角色</th>
                <th>状态</th>
                <th>失败次数</th>
                <th>最近登录</th>
                <th class="ops-col">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="u in users" :key="u.username">
                <td>
                  <span class="uname">{{ u.username }}</span>
                  <n-tag v-if="u.is_demo" size="tiny" type="info" :bordered="false">演示</n-tag>
                  <n-tag
                    v-if="u.username === auth.userId"
                    size="tiny"
                    :bordered="false"
                    class="me-tag"
                  >我</n-tag>
                </td>
                <td>
                  <n-tag size="small" :type="u.role === 'admin' ? 'warning' : 'default'" :bordered="false">
                    {{ u.role === "admin" ? "管理员" : "普通用户" }}
                  </n-tag>
                </td>
                <td>
                  <n-tag v-if="u.locked" size="small" type="error" :bordered="false">已锁定</n-tag>
                  <n-tag v-else-if="!u.is_active" size="small" :bordered="false">已停用</n-tag>
                  <n-tag v-else size="small" type="success" :bordered="false">正常</n-tag>
                </td>
                <td class="num">{{ u.failed_attempts }}</td>
                <td class="muted">{{ fmt(u.last_login_at) }}</td>
                <td class="ops">
                  <n-button text size="tiny" @click="openReset(u.username)">重置口令</n-button>
                  <n-button
                    v-if="u.locked"
                    text
                    size="tiny"
                    type="primary"
                    @click="patchUser(u, { unlock: true }, '已解锁')"
                  >解锁</n-button>
                  <n-button
                    v-if="u.role !== 'admin'"
                    text
                    size="tiny"
                    @click="patchUser(u, { role: 'admin' }, '已设为管理员')"
                  >设管理员</n-button>
                  <n-button
                    v-else
                    text
                    size="tiny"
                    @click="patchUser(u, { role: 'user' }, '已取消管理员')"
                  >降为用户</n-button>
                  <n-button
                    v-if="u.is_active"
                    text
                    size="tiny"
                    type="warning"
                    @click="patchUser(u, { is_active: false }, '已停用')"
                  >停用</n-button>
                  <n-button
                    v-else
                    text
                    size="tiny"
                    type="primary"
                    @click="patchUser(u, { is_active: true }, '已启用')"
                  >启用</n-button>
                  <n-popconfirm @positive-click="removeUser(u)">
                    <template #trigger>
                      <n-button text size="tiny" type="error">删除</n-button>
                    </template>
                    确认删除「{{ u.username }}」?该账号将无法登录。
                  </n-popconfirm>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </n-spin>
    </main>

    <!-- 新建 -->
    <n-modal v-model:show="showCreate" preset="card" title="新建用户" style="width: 380px">
      <div class="form-rows">
        <label>用户名</label>
        <n-input v-model:value="cUser" placeholder="中文 / 字母 / 数字 / 下划线" />
        <label>初始口令</label>
        <n-input v-model:value="cPwd" type="password" show-password-on="click" placeholder="至少 6 位" />
        <label>角色</label>
        <n-select v-model:value="cRole" :options="roleOptions" />
      </div>
      <template #footer>
        <div class="modal-actions">
          <n-button :disabled="creating" @click="showCreate = false">取消</n-button>
          <n-button type="primary" :loading="creating" @click="onCreate">创建</n-button>
        </div>
      </template>
    </n-modal>

    <!-- 重置口令 -->
    <n-modal v-model:show="showReset" preset="card" :title="`重置「${resetTarget}」口令`" style="width: 360px">
      <n-input
        v-model:value="resetPwd"
        type="password"
        show-password-on="click"
        placeholder="新口令,至少 6 位"
        @keyup.enter="onReset"
      />
      <template #footer>
        <div class="modal-actions">
          <n-button :disabled="resetting" @click="showReset = false">取消</n-button>
          <n-button type="primary" :loading="resetting" @click="onReset">重置</n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>

<style scoped>
.admin-wrap {
  min-height: 100%;
  background: #eef3f2;
  display: flex;
  flex-direction: column;
}
.bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  height: 60px;
  background: linear-gradient(120deg, #1f5f5e, #2f8b89);
  color: #fff;
}
.bar-left {
  display: flex;
  align-items: baseline;
  gap: 10px;
}
.bar-left .logo {
  font-size: 22px;
}
.bar-left h1 {
  font-size: 19px;
  font-weight: 700;
  margin: 0;
}
.bar-left .sub {
  font-size: 12px;
  opacity: 0.8;
}
.bar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}
.bar-right .me {
  font-size: 13px;
  opacity: 0.9;
  margin-right: 4px;
}
.bar-right :deep(.n-button) {
  color: #fff;
}
.body {
  flex: 1;
  width: 100%;
  max-width: 1080px;
  margin: 0 auto;
  padding: 22px 24px 40px;
}
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}
.stat {
  color: #46615f;
  font-size: 14px;
}
.actions {
  display: flex;
  gap: 8px;
}
.table-card {
  background: #fff;
  border-radius: 14px;
  box-shadow: 0 6px 22px rgba(20, 64, 63, 0.08);
  overflow: hidden;
}
.tbl {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}
.tbl thead th {
  text-align: left;
  padding: 13px 16px;
  background: #f4f8f7;
  color: #5b736f;
  font-weight: 600;
  border-bottom: 1px solid #e6efed;
}
.tbl tbody td {
  padding: 12px 16px;
  border-bottom: 1px solid #f0f5f4;
  vertical-align: middle;
}
.tbl tbody tr:last-child td {
  border-bottom: none;
}
.tbl tbody tr:hover {
  background: #f8fbfa;
}
.uname {
  font-weight: 600;
  color: #14403f;
  margin-right: 6px;
}
.me-tag {
  background: #e3f0ee;
  color: #2f8b89;
}
.num {
  text-align: center;
}
.muted {
  color: #8a9b98;
  font-size: 13px;
}
.ops-col {
  width: 320px;
}
.ops {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}
.form-rows {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.form-rows label {
  font-size: 13px;
  color: #5b736f;
  margin-top: 6px;
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
