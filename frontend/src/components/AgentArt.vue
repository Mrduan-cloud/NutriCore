<script setup lang="ts">
/* 4 个子 Agent 的「彩色徽标插画」—— 渐变圆角瓷砖 + 白色线性徽标(类 app-icon)。
   用在欢迎页能力卡上,给每个 Agent 一个专属配色与画面,告别灰线单调。
   每个 Agent 配色:
     consult   营养咨询 → 青绿(沟通/清新)
     screening 风险筛查 → 琥珀(评估/提醒)
     plan      膳食方案 → 嫩绿(餐食/健康)
     insight   数据洞察 → 紫罗兰(数据/洞见)
   渐变 id 带 name 后缀,避免多实例冲突。 */
defineProps<{ name: string; size?: number }>();
</script>

<template>
  <svg
    :width="size || 56"
    :height="size || 56"
    viewBox="0 0 48 48"
    fill="none"
    aria-hidden="true"
  >
    <defs>
      <linearGradient :id="`art-${name}`" x1="0" y1="0" x2="1" y2="1">
        <template v-if="name === 'consult'">
          <stop offset="0" stop-color="#5eead4" />
          <stop offset="1" stop-color="#13b3a6" />
        </template>
        <template v-else-if="name === 'screening'">
          <stop offset="0" stop-color="#fcd34d" />
          <stop offset="1" stop-color="#f59e0b" />
        </template>
        <template v-else-if="name === 'plan'">
          <stop offset="0" stop-color="#86efac" />
          <stop offset="1" stop-color="#22c55e" />
        </template>
        <template v-else>
          <stop offset="0" stop-color="#c4b5fd" />
          <stop offset="1" stop-color="#7c6cf0" />
        </template>
      </linearGradient>
    </defs>

    <!-- 彩色瓷砖 + 顶部高光 -->
    <rect x="2" y="2" width="44" height="44" rx="13" :fill="`url(#art-${name})`" />
    <path d="M2 15a13 13 0 0 1 13-13h18a13 13 0 0 1 11 6 44 44 0 0 0-42 7Z" fill="#fff" opacity="0.14" />

    <!-- 白色徽标(24 视窗路径,平移 12 居中于瓷砖) -->
    <g
      transform="translate(12 12)"
      stroke="#fff"
      stroke-width="1.9"
      stroke-linecap="round"
      stroke-linejoin="round"
      fill="none"
    >
      <!-- 营养咨询:对话气泡 + 内含一片小叶(沟通 + 营养) -->
      <template v-if="name === 'consult'">
        <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
        <path d="M9 13c0-2 1.5-3.5 3.5-3.5 0 2-1.5 3.5-3.5 3.5Z" />
      </template>
      <!-- 风险筛查:评估问卷 + 勾 -->
      <template v-else-if="name === 'screening'">
        <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" />
        <rect x="8" y="2" width="8" height="4" rx="1" />
        <path d="m9 13.5 2 2 4-4" />
      </template>
      <!-- 膳食方案:沙拉碗 + 升腾热气(餐食/健康) -->
      <template v-else-if="name === 'plan'">
        <path d="M3 12h18a9 9 0 0 1-18 0Z" />
        <path d="M2.5 12h19" />
        <path d="M9 5.5c0-1 .8-1.8 0-3M14 6c0-1 .8-1.8 0-3" />
      </template>
      <!-- 数据洞察:柱状图 -->
      <template v-else>
        <line x1="6" y1="20" x2="6" y2="13" />
        <line x1="12" y1="20" x2="12" y2="5" />
        <line x1="18" y1="20" x2="18" y2="10" />
      </template>
    </g>
  </svg>
</template>
