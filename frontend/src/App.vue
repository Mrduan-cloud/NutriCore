<script setup lang="ts">
import { NConfigProvider, NMessageProvider, zhCN, dateZhCN } from "naive-ui";
import { RouterView } from "vue-router";

// NutriCore 主题:营养健康 → 绿色系
const themeOverrides = {
  common: {
    primaryColor: "#2F8B89",
    primaryColorHover: "#3AA3A0",
    primaryColorPressed: "#26716F",
    borderRadius: "10px",
  },
};
</script>

<template>
  <n-config-provider :locale="zhCN" :date-locale="dateZhCN" :theme-overrides="themeOverrides">
    <n-message-provider>
      <RouterView />
    </n-message-provider>
  </n-config-provider>
</template>

<style>
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
</style>
