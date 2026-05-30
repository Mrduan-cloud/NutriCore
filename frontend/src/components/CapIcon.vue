<script setup lang="ts">
/* 4 个子 Agent 的功能图标 —— Lucide/Feather 风格 monochrome stroke SVG,
   取代原先的 emoji(💬📋🍱📊),与品牌绿协调、显得更正式。currentColor 跟随父级文字色。 */
defineProps<{ name: string; size?: number }>();
</script>

<template>
  <svg
    :width="size || 18"
    :height="size || 18"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.8"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <!-- 营养咨询:对话气泡 -->
    <template v-if="name === 'consult'">
      <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
    </template>
    <!-- 风险筛查:带勾的评估问卷(NRS-2002 是量表问答) -->
    <template v-else-if="name === 'screening'">
      <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" />
      <rect x="8" y="2" width="8" height="4" rx="1" />
      <path d="m9 14 2 2 4-4" />
    </template>
    <!-- 膳食方案:刀叉(餐食) -->
    <template v-else-if="name === 'plan'">
      <path d="M3 2v7c0 1.1.9 2 2 2h0a2 2 0 0 0 2-2V2" />
      <path d="M7 2v20" />
      <path d="M21 15V2a5 5 0 0 0-5 5v6c0 1.1.9 2 2 2h3Zm0 0v7" />
    </template>
    <!-- 数据洞察:柱状图 -->
    <template v-else-if="name === 'insight'">
      <line x1="6" y1="20" x2="6" y2="14" />
      <line x1="12" y1="20" x2="12" y2="4" />
      <line x1="18" y1="20" x2="18" y2="10" />
    </template>
    <!-- 兜底:小圆点 -->
    <template v-else>
      <circle cx="12" cy="12" r="3" />
    </template>
  </svg>
</template>
