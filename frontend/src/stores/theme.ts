import { defineStore } from "pinia";
import { ref, watch } from "vue";

const KEY = "nutricore_theme";
export type ThemeName = "light" | "dark";

export const useThemeStore = defineStore("theme", () => {
  // 默认浅色(原始配色,观感稳);深色作为可选开关。
  const theme = ref<ThemeName>((localStorage.getItem(KEY) as ThemeName) || "light");

  function apply(t: ThemeName) {
    document.documentElement.setAttribute("data-theme", t);
  }
  apply(theme.value);

  watch(theme, (t) => {
    localStorage.setItem(KEY, t);
    apply(t);
  });

  function toggle() {
    theme.value = theme.value === "dark" ? "light" : "dark";
  }

  return { theme, toggle };
});
