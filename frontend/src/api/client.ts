import axios from "axios";
import { useAuthStore } from "@/stores/auth";

// 统一 axios 实例。开发期 baseURL 留空,走 vite proxy(/api → :8000)。
const client = axios.create({
  baseURL: "",
  timeout: 120000, // LLM 对话可能较慢,给足超时
});

// 请求拦截器:自动带上 JWT
client.interceptors.request.use((config) => {
  const auth = useAuthStore();
  if (auth.token) {
    config.headers.Authorization = `Bearer ${auth.token}`;
  }
  return config;
});

// 响应拦截器:401 自动登出
client.interceptors.response.use(
  (resp) => resp,
  (error) => {
    if (error.response?.status === 401) {
      const auth = useAuthStore();
      auth.logout();
    }
    return Promise.reject(error);
  },
);

export default client;
