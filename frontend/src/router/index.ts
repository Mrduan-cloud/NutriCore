import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "@/stores/auth";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/chat" },
    {
      path: "/login",
      name: "login",
      component: () => import("@/views/LoginView.vue"),
    },
    {
      path: "/chat",
      name: "chat",
      component: () => import("@/views/ChatView.vue"),
      meta: { requiresAuth: true },
    },
    {
      path: "/admin",
      name: "admin",
      component: () => import("@/views/AdminView.vue"),
      meta: { requiresAuth: true, requiresAdmin: true },
    },
    {
      // 公开分享:无鉴权,直接凭 token 看 Q&A 快照
      path: "/s/:token",
      name: "share",
      component: () => import("@/views/ShareView.vue"),
      meta: { public: true },
    },
  ],
});

// 路由守卫:未登录访问受保护页 → 跳登录;非管理员访问后台 → 回对话
router.beforeEach((to) => {
  const auth = useAuthStore();
  if (to.meta.requiresAuth && !auth.token) {
    return { name: "login" };
  }
  if (to.meta.requiresAdmin && !auth.isAdmin) {
    return { name: "chat" };
  }
  if (to.name === "login" && auth.token) {
    return { name: auth.isAdmin ? "admin" : "chat" };
  }
});

export default router;
