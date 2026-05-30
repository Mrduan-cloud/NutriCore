import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

// 开发期把 /api 代理到本地后端(docker compose 暴露在 8000)。
// 生产打包后由后端 StaticFiles 或 nginx 托管 dist/。
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: 5173,
    // 开发期允许任意 Host 访问(docker 内截图 / 内网联调 / Cloudflare Tunnel 演示)
    allowedHosts: true,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
