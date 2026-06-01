<script setup lang="ts">
import { ref, computed, watch } from "vue";
import { NModal, NSpin, NButton, useMessage } from "naive-ui";
import QRCode from "qrcode";

const props = defineProps<{
  show: boolean;
  url: string; // 公开分享 URL(空串表示正在生成中)
  title: string; // 用于社交平台分享的标题
  loading?: boolean;
}>();
const emit = defineEmits<{ (e: "update:show", v: boolean): void }>();

const message = useMessage();

const visible = computed({
  get: () => props.show,
  set: (v) => emit("update:show", v),
});

// 复制链接
const copied = ref(false);
async function copyLink() {
  if (!props.url) return;
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(props.url);
    } else {
      const ta = document.createElement("textarea");
      ta.value = props.url;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    }
    copied.value = true;
    message.success("链接已复制");
    setTimeout(() => (copied.value = false), 2000);
  } catch {
    message.warning("复制失败,请手动选择链接复制");
  }
}

// 各社交平台 intent URL —— 直接打开新窗口,平台自带分享面板
const enc = encodeURIComponent;
function openWeibo() {
  window.open(
    `https://service.weibo.com/share/share.php?url=${enc(props.url)}&title=${enc(props.title)}`,
    "_blank",
    "noopener,width=720,height=540",
  );
}
function openTwitter() {
  window.open(
    `https://twitter.com/intent/tweet?text=${enc(props.title)}&url=${enc(props.url)}`,
    "_blank",
    "noopener,width=620,height=480",
  );
}
function openLinkedIn() {
  window.open(
    `https://www.linkedin.com/sharing/share-offsite/?url=${enc(props.url)}`,
    "_blank",
    "noopener,width=720,height=560",
  );
}
function openEmail() {
  window.location.href = `mailto:?subject=${enc(props.title)}&body=${enc(props.title + "\n\n" + props.url)}`;
}

// 微信:桌面浏览器无法直接调起,生成二维码让用户扫码 → 手机微信里直接分享
const qrOpen = ref(false);
const qrDataUrl = ref("");
async function shareWeChat() {
  qrOpen.value = true;
  try {
    qrDataUrl.value = await QRCode.toDataURL(props.url, {
      width: 280,
      margin: 1,
      color: { dark: "#14403f", light: "#ffffff" },
    });
  } catch {
    qrDataUrl.value = "";
    message.error("二维码生成失败");
  }
}

// 系统分享面板(移动端命中已装应用的分享列表)
const nativeShareAvailable = typeof navigator !== "undefined" && "share" in navigator;
async function nativeShare() {
  try {
    await (navigator as any).share({ title: props.title, url: props.url });
  } catch {
    /* 用户取消,无需打扰 */
  }
}

watch(visible, (v) => {
  if (!v) {
    copied.value = false;
    qrOpen.value = false;
  }
});
</script>

<template>
  <n-modal v-model:show="visible" preset="card" title="分享这条回复" style="max-width: 460px">
    <div v-if="loading || !url" class="loading">
      <n-spin />
      <span class="loading-text">正在生成分享链接…</span>
    </div>

    <div v-else>
      <div class="link-row">
        <input :value="url" readonly class="link-input" @focus="($event.target as HTMLInputElement).select()" />
        <n-button :type="copied ? 'success' : 'primary'" @click="copyLink">
          {{ copied ? "✓ 已复制" : "复制链接" }}
        </n-button>
      </div>
      <p class="hint">
        🔒 链接公开可访问,<b>不包含</b>你的用户名 / 健康档案 / 历史对话。任何人凭链接可看到这一问一答。
      </p>

      <div class="channel-label">分享到</div>
      <div class="channels">
        <button class="ch wechat" title="微信(显示二维码)" @click="shareWeChat">
          <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
            <path fill="#07C160" d="M8.691 2.188C3.891 2.188 0 5.476 0 9.53c0 2.212 1.17 4.203 3.002 5.55a.59.59 0 0 1 .213.665l-.39 1.48c-.019.07-.048.141-.048.213 0 .163.13.295.29.295a.326.326 0 0 0 .167-.054l1.903-1.114a.864.864 0 0 1 .717-.098 10.16 10.16 0 0 0 2.837.403c.276 0 .543-.027.812-.05-.857-2.578.157-4.972 1.932-6.446 1.703-1.415 3.882-1.98 6.099-1.838-.485-3.499-3.769-6.197-7.643-6.345zM5.785 5.991c.642 0 1.162.529 1.162 1.18a1.17 1.17 0 0 1-1.162 1.178A1.17 1.17 0 0 1 4.623 7.17c0-.651.52-1.18 1.162-1.18zm5.813 0c.642 0 1.162.529 1.162 1.18a1.17 1.17 0 0 1-1.162 1.178 1.17 1.17 0 0 1-1.162-1.178c0-.651.52-1.18 1.162-1.18zm5.34 2.867c-1.797-.052-3.746.512-5.28 1.786-1.72 1.428-2.687 3.72-1.78 6.22.942 2.453 3.666 4.229 6.884 4.229.826 0 1.622-.12 2.361-.336a.722.722 0 0 1 .598.082l1.584.926a.272.272 0 0 0 .14.047c.134 0 .24-.111.24-.247 0-.06-.023-.12-.038-.177-.005-.024-.327-1.233-.327-1.233a.582.582 0 0 1-.023-.156.49.49 0 0 1 .201-.398C23.024 16.55 24 14.9 24 13.061c0-3.359-3.122-6.078-7.062-6.203zm-2.157 2.642c.535 0 .969.44.969.984a.976.976 0 0 1-.969.984.976.976 0 0 1-.969-.984c0-.544.434-.984.969-.984zm4.844 0c.535 0 .969.44.969.984a.976.976 0 0 1-.969.984.976.976 0 0 1-.969-.984c0-.544.434-.984.969-.984z"/>
          </svg>
          <span class="ch-name">微信</span>
        </button>
        <button class="ch weibo" title="微博" @click="openWeibo">
          <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
            <path fill="#E6162D" d="M10.098 20.323c-3.977.391-7.414-1.406-7.672-4.02-.259-2.609 2.759-5.047 6.74-5.441 3.979-.394 7.413 1.404 7.671 4.018.259 2.6-2.759 5.049-6.737 5.443h-.002zM9.05 17.219c-.384.616-1.208.884-1.829.602-.612-.279-.793-.991-.406-1.593.379-.595 1.176-.861 1.793-.601.622.263.821.972.442 1.592zm1.27-1.627c-.141.237-.449.353-.689.253-.236-.09-.313-.36-.177-.586.138-.227.436-.34.672-.244.239.09.319.351.18.587l.014-.01zm.176-2.719c-1.893-.493-4.033.45-4.857 2.118-.836 1.704-.026 3.591 1.886 4.21 1.983.64 4.318-.341 5.132-2.179.8-1.793-.201-3.642-2.161-4.149zm7.563-1.224c-.346-.105-.57-.18-.405-.615.375-.977.42-1.821 0-2.42-.781-1.126-2.917-1.067-5.364-.045 0 0-.766.331-.571-.271.376-1.193.315-2.189-.27-2.766-1.297-1.305-4.745.034-7.701 2.984C1.527 8.737 0 11.078 0 13.101c0 3.876 5.024 6.232 9.939 6.232 6.444 0 10.733-3.71 10.733-6.659 0-1.781-1.518-2.79-2.61-3.06l-.005-.004zm1.532-2.879c-.589-.648-1.461-.896-2.268-.72-.418.09-.681.5-.591.917.09.414.501.677.918.586.396-.084.81.029 1.084.35.27.32.343.745.193 1.13-.149.404.063.852.469.998.4.149.847-.063.998-.47.314-.797.149-1.733-.443-2.376l-.36-.415zm1.434-1.444c-1.213-1.34-3.007-1.851-4.66-1.501-.484.105-.79.585-.687 1.07.105.481.585.79 1.066.689 1.182-.252 2.453.121 3.314 1.066.857.954 1.08 2.255.667 3.394-.166.464.075.974.539 1.139.467.165.975-.076 1.141-.54.591-1.612.262-3.444-.93-4.766l-.45-.551z"/>
          </svg>
          <span class="ch-name">微博</span>
        </button>
        <button class="ch x" title="X / Twitter" @click="openTwitter">
          <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
            <path fill="#000000" d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
          </svg>
          <span class="ch-name">X</span>
        </button>
        <button class="ch linkedin" title="LinkedIn" @click="openLinkedIn">
          <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
            <path fill="#0A66C2" d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 0 1-2.063-2.065 2.063 2.063 0 1 1 2.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/>
          </svg>
          <span class="ch-name">LinkedIn</span>
        </button>
        <button class="ch email" title="邮件" @click="openEmail">
          <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="#5b736f" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <rect x="2.5" y="4.5" width="19" height="15" rx="2"/>
            <path d="M3 6.5l9 7 9-7"/>
          </svg>
          <span class="ch-name">邮件</span>
        </button>
        <button v-if="nativeShareAvailable" class="ch native" title="系统分享面板" @click="nativeShare">
          <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="#5b736f" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M4 12v7a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-7"/>
            <polyline points="16 6 12 2 8 6"/>
            <line x1="12" y1="2" x2="12" y2="15"/>
          </svg>
          <span class="ch-name">更多</span>
        </button>
      </div>
    </div>

    <!-- 微信二维码子弹层(扫码 → 手机微信里直接分享给好友 / 朋友圈) -->
    <n-modal v-model:show="qrOpen" preset="card" title="用微信扫一扫" style="width: 360px">
      <div class="qr-wrap">
        <div v-if="!qrDataUrl" class="qr-loading"><n-spin /></div>
        <img v-else :src="qrDataUrl" alt="WeChat QR" class="qr-img" />
        <p class="qr-hint">
          打开微信 → 扫一扫 → 在聊天 / 朋友圈分享给好友<br />
          也可以直接<a href="#" @click.prevent="copyLink">复制链接</a>到微信粘贴
        </p>
      </div>
    </n-modal>
  </n-modal>
</template>

<style scoped>
.loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 30px 0;
  color: #6b8b88;
}
.link-row {
  display: flex;
  gap: 8px;
  align-items: center;
}
.link-input {
  flex: 1 1 auto;
  min-width: 0;
  background: #f4f8f7;
  border: 1px solid #dce7e5;
  border-radius: 8px;
  padding: 9px 12px;
  font-size: 13px;
  color: #1f333a;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  outline: none;
}
.link-input:focus {
  border-color: #2f8b89;
}
.hint {
  margin: 10px 0 18px;
  font-size: 12.5px;
  color: #8a9b98;
  line-height: 1.6;
}
.channel-label {
  font-size: 12.5px;
  color: #6b8b88;
  margin-bottom: 8px;
}
.channels {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}
.ch {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  background: #fafdfc;
  border: 1px solid #e6efed;
  border-radius: 10px;
  padding: 12px 6px;
  cursor: pointer;
  transition: all 0.14s;
}
.ch:hover {
  background: #fff;
  border-color: #2f8b89;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(47, 139, 137, 0.14);
}
.ch svg {
  display: block;
}
.ch-name {
  font-size: 12.5px;
  color: #14403f;
  font-weight: 500;
}

/* QR 子弹层 */
.qr-wrap {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
  padding: 6px 0 4px;
}
.qr-loading {
  width: 280px;
  height: 280px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.qr-img {
  width: 280px;
  height: 280px;
  border: 1px solid #e6efed;
  border-radius: 10px;
  background: #fff;
  padding: 6px;
}
.qr-hint {
  font-size: 12.5px;
  color: #6b8b88;
  line-height: 1.7;
  text-align: center;
  margin: 0;
}
.qr-hint a {
  color: #2f8b89;
  text-decoration: none;
  font-weight: 600;
}
.qr-hint a:hover {
  text-decoration: underline;
}
</style>
