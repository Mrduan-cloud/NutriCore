import { defineStore } from "pinia";
import { ref } from "vue";
import axios from "axios";

const TOKEN_KEY = "nutricore_token";
const USER_KEY = "nutricore_user";

export const useAuthStore = defineStore("auth", () => {
  const token = ref<string>(localStorage.getItem(TOKEN_KEY) || "");
  const userId = ref<string>(localStorage.getItem(USER_KEY) || "");

  async function login(username: string, password: string) {
    // 登录用裸 axios(此时还没 token,也避免拦截器循环依赖)
    const { data } = await axios.post("/api/auth/login", { username, password });
    token.value = data.access_token;
    userId.value = data.user_id;
    localStorage.setItem(TOKEN_KEY, token.value);
    localStorage.setItem(USER_KEY, userId.value);
  }

  function logout() {
    token.value = "";
    userId.value = "";
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  }

  return { token, userId, login, logout };
});
