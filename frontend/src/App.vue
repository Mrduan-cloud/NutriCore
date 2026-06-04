<script setup lang="ts">
import { NConfigProvider, NMessageProvider, darkTheme, zhCN, dateZhCN } from "naive-ui";
import { RouterView } from "vue-router";

// NutriCore 主题:营养健康 → 深色高级风 + 翠绿(emerald)点缀。
// 近黑底 + 翠绿辉光,与 MediRead 同一套深色语言,主色换成营养健康调性。
const themeOverrides = {
  common: {
    primaryColor: "#34d399",
    primaryColorHover: "#6ee7b7",
    primaryColorPressed: "#10b981",
    primaryColorSuppl: "#34d399",
    bodyColor: "#0a0f0d",
    cardColor: "rgba(255, 255, 255, 0.03)",
    modalColor: "#101613",
    popoverColor: "#121815",
    borderRadius: "10px",
    fontSize: "14px",
  },
  Card: {
    color: "rgba(255, 255, 255, 0.03)",
    borderColor: "rgba(255, 255, 255, 0.08)",
  },
};
</script>

<template>
  <n-config-provider
    :theme="darkTheme"
    :locale="zhCN"
    :date-locale="dateZhCN"
    :theme-overrides="themeOverrides"
  >
    <n-message-provider>
      <RouterView />
    </n-message-provider>
  </n-config-provider>
</template>

<style>
/* 深色设计令牌 —— 各 view 的 scoped 样式统一引用,改一处全局生效 */
:root {
  --nc-bg: #0a0f0d;
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
  background-image: radial-gradient(
    60rem 40rem at 50% -12rem,
    rgba(52, 211, 153, 0.08),
    transparent 70%
  );
  background-repeat: no-repeat;
  background-attachment: fixed;
}
::selection {
  background: rgba(52, 211, 153, 0.24);
}
::-webkit-scrollbar {
  width: 10px;
  height: 10px;
}
::-webkit-scrollbar-thumb {
  background: #243029;
  border-radius: 9999px;
  border: 2px solid var(--nc-bg);
}
::-webkit-scrollbar-thumb:hover {
  background: #34463c;
}
</style>
