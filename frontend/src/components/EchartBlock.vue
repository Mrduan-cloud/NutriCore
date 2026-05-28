<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch, nextTick } from "vue";
import * as echarts from "echarts";

// 渲染后端 data_insight 下发的 ECharts 配置。option 为完整 ECharts option 对象。
const props = defineProps<{ option: Record<string, any> | null | undefined }>();

const el = ref<HTMLDivElement | null>(null);
let chart: echarts.ECharts | null = null;

function render() {
  if (!el.value || !props.option) return;
  if (!chart) chart = echarts.init(el.value);
  // 统一一点主题色,贴合页面青绿色调
  const themed = {
    color: ["#2F8B89"],
    textStyle: { fontFamily: "inherit" },
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
  window.addEventListener("resize", onResize);
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", onResize);
  chart?.dispose();
  chart = null;
});

watch(() => props.option, render, { deep: true });
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
</style>
