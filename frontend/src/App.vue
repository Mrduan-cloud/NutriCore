<script setup lang="ts">
import { computed } from "vue";
import { NConfigProvider, NMessageProvider, darkTheme, zhCN, dateZhCN } from "naive-ui";
import { RouterView } from "vue-router";
import { useThemeStore } from "@/stores/theme";

const themeStore = useThemeStore();
const isDark = computed(() => themeStore.theme === "dark");
const naiveTheme = computed(() => (isDark.value ? darkTheme : null));

// 营养健康主色:浅色用原青绿 #2f8b89,深色用更亮的翠绿 #34d399(暗底上更跳)。
const themeOverrides = computed(() => {
  const base = isDark.value
    ? {
        primaryColor: "#34d399",
        primaryColorHover: "#6ee7b7",
        primaryColorPressed: "#10b981",
        primaryColorSuppl: "#34d399",
        bodyColor: "#0a1411",
        cardColor: "rgba(255, 255, 255, 0.03)",
        modalColor: "#101613",
        popoverColor: "#121815",
      }
    : {
        primaryColor: "#2f8b89",
        primaryColorHover: "#3aa3a0",
        primaryColorPressed: "#26716f",
        primaryColorSuppl: "#2f8b89",
      };
  return { common: { ...base, borderRadius: "10px" } };
});
</script>

<template>
  <n-config-provider
    :theme="naiveTheme"
    :locale="zhCN"
    :date-locale="dateZhCN"
    :theme-overrides="themeOverrides"
  >
    <n-message-provider>
      <RouterView />
      <button
        class="global-theme-toggle"
        :title="isDark ? '切换到浅色' : '切换到深色'"
        :aria-label="isDark ? '切换到浅色' : '切换到深色'"
        @click="themeStore.toggle"
      >
        <svg
          v-if="isDark"
          viewBox="0 0 24 24"
          width="18"
          height="18"
          fill="none"
          stroke="currentColor"
          stroke-width="1.8"
          stroke-linecap="round"
          stroke-linejoin="round"
          aria-hidden="true"
        >
          <circle cx="12" cy="12" r="4" />
          <path
            d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"
          />
        </svg>
        <svg
          v-else
          viewBox="0 0 24 24"
          width="18"
          height="18"
          fill="none"
          stroke="currentColor"
          stroke-width="1.8"
          stroke-linecap="round"
          stroke-linejoin="round"
          aria-hidden="true"
        >
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
        </svg>
      </button>
    </n-message-provider>
  </n-config-provider>
</template>

<style>
/* ============ 主题设计令牌 ============
   :root = 浅色(默认,原始配色);[data-theme="dark"] = 深色。
   各 view 的 scoped 样式统一引用 --nc-*,切换时整站随之翻转。 */
:root {
  --nc-bg: #eef3f2;
  --nc-surface: #ffffff;
  --nc-surface-2: #f4f8f7;
  --nc-border: #e6efed;
  --nc-border-strong: #d6e9e7;
  --nc-text: #14403f;
  --nc-text-muted: #6b7280;
  --nc-text-dim: #9ca3af;
  --nc-accent: #2f8b89;
  --nc-accent-2: #3aa3a0;
  --nc-accent-soft: rgba(47, 139, 137, 0.1);
  --nc-accent-border: rgba(47, 139, 137, 0.26);
  --nc-on-accent: #ffffff;
  --nc-hover: rgba(20, 64, 63, 0.06);
  --nc-shadow: rgba(20, 64, 63, 0.1);
  /* 主区/欢迎区柔光(浅色:极淡;深色:翠绿辉光) */
  --nc-page: radial-gradient(1200px 600px at 70% -10%, #eef6f4 0%, #f4f7f6 45%, #eef2f1 100%);
  --nc-composer-fade: #eef3f2;
  --nc-composer-fade-0: rgba(238, 243, 242, 0);
}
:root[data-theme="dark"] {
  --nc-bg: #0a1411;
  --nc-surface: rgba(255, 255, 255, 0.03);
  --nc-surface-2: rgba(255, 255, 255, 0.05);
  --nc-border: rgba(255, 255, 255, 0.08);
  --nc-border-strong: rgba(255, 255, 255, 0.14);
  --nc-text: #e8ecea;
  --nc-text-muted: #94a3a0;
  --nc-text-dim: #6b7c78;
  --nc-accent: #34d399;
  --nc-accent-2: #6ee7b7;
  --nc-accent-soft: rgba(52, 211, 153, 0.12);
  --nc-accent-border: rgba(52, 211, 153, 0.3);
  --nc-on-accent: #07140e;
  --nc-hover: rgba(255, 255, 255, 0.06);
  --nc-shadow: rgba(0, 0, 0, 0.4);
  --nc-page: radial-gradient(1100px 600px at 72% -12%, rgba(52, 211, 153, 0.07) 0%, transparent 55%), #0a1411;
  --nc-composer-fade: #0a1411;
  --nc-composer-fade-0: rgba(10, 20, 17, 0);
}

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}
html,
body,
#app {
  height: 100%;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
    "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
}
body {
  background-color: var(--nc-bg);
  color: var(--nc-text);
  -webkit-font-smoothing: antialiased;
  transition: background-color 0.25s ease, color 0.25s ease;
}

/* 全局悬浮主题切换钮 —— 任意页面右上角常驻 */
.global-theme-toggle {
  position: fixed;
  top: 14px;
  right: 16px;
  z-index: 200;
  width: 38px;
  height: 38px;
  border-radius: 11px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--nc-text-muted);
  cursor: pointer;
  background: var(--nc-surface);
  border: 1px solid var(--nc-border-strong);
  box-shadow: 0 4px 16px var(--nc-shadow);
  transition: transform 0.14s, border-color 0.14s, color 0.14s;
}
.global-theme-toggle:hover {
  transform: translateY(-1px) scale(1.04);
  border-color: var(--nc-accent);
  color: var(--nc-accent);
}
</style>
