<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch, nextTick } from "vue";
import * as echarts from "echarts";
import { useThemeStore } from "@/stores/theme";

// 渲染后端 data_insight 下发的 ECharts 配置。option 为完整 ECharts option 对象。
const props = defineProps<{ option: Record<string, any> | null | undefined }>();
const themeStore = useThemeStore();

const el = ref<HTMLDivElement | null>(null);
let chart: echarts.ECharts | null = null;
let ro: ResizeObserver | null = null;

function render() {
  if (!el.value || !props.option) return;
  const dark = themeStore.theme === "dark";
  // 主题切换时重建实例 —— echarts 内置 dark/light 主题仅在 init 时生效
  if (chart) {
    chart.dispose();
    chart = null;
  }
  chart = echarts.init(el.value, dark ? "dark" : undefined);
  const themed = {
    color: [dark ? "#34d399" : "#2F8B89"],
    backgroundColor: "transparent",
    textStyle: { fontFamily: "inherit", color: dark ? "#cbd5e1" : "#374151" },
    ...props.option,
  };
  chart.setOption(themed, true);
  chart.resize();
}

function onResize() {
  chart?.resize();
}

onMounted(async () => {
  await nextTick();
  render();
  // 回看历史会话时,容器可能在 init 时还没拿到尺寸 → echarts 画成空白。
  // 用 ResizeObserver 在容器拿到尺寸/变化后补一次 resize,确保图能画出来。
  if (el.value && "ResizeObserver" in window) {
    ro = new ResizeObserver(() => chart?.resize());
    ro.observe(el.value);
  }
  window.addEventListener("resize", onResize);
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", onResize);
  ro?.disconnect();
  ro = null;
  chart?.dispose();
  chart = null;
});

watch(() => props.option, render, { deep: true });
watch(() => themeStore.theme, render);
</script>

<template>
  <div ref="el" class="echart" />
</template>

<style scoped>
.echart {
  width: 100%;
  height: 260px;
  margin-top: 12px;
  border: 1px solid #eef2f2;
  border-radius: 10px;
  background: #fbfdfd;
}

/* ============ 深色主题覆盖 ============ */
[data-theme="dark"] .echart {
  border-color: var(--nc-border);
  background: var(--nc-surface);
}
</style>
