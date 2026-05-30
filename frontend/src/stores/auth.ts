import { defineStore } from "pinia";
import { computed, ref } from "vue";
import axios from "axios";

const TOKEN_KEY = "nutricore_token";
const USER_KEY = "nutricore_user";
const ROLE_KEY = "nutricore_role";
const AVATAR_KEY = "nutricore_avatar_style";

export const useAuthStore = defineStore("auth", () => {
  const token = ref<string>(localStorage.getItem(TOKEN_KEY) || "");
  const userId = ref<string>(localStorage.getItem(USER_KEY) || "");
  const role = ref<string>(localStorage.getItem(ROLE_KEY) || "user");
  const avatarStyle = ref<string>(localStorage.getItem(AVATAR_KEY) || "avataaars");

  const isAdmin = computed(() => role.value === "admin");

  function setAvatarStyle(style: string) {
    avatarStyle.value = style;
    localStorage.setItem(AVATAR_KEY, style);
  }

  function _apply(data: { access_token: string; user_id: string; role?: string }) {
    token.value = data.access_token;
    userId.value = data.user_id;
    role.value = data.role || "user";
    localStorage.setItem(TOKEN_KEY, token.value);
    localStorage.setItem(USER_KEY, userId.value);
    localStorage.setItem(ROLE_KEY, role.value);
  }

  async function login(username: string, password: string) {
    // 登录用裸 axios(此时还没 token,也避免拦截器循环依赖)
    const { data } = await axios.post("/api/auth/login", { username, password });
    _apply(data);
  }

  // 自助注册:成功后直接登录(后端随注册下发 token)
  async function register(username: string, password: string) {
    const { data } = await axios.post("/api/auth/register", { username, password });
    _apply(data);
  }

  function logout() {
    token.value = "";
    userId.value = "";
    role.value = "user";
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    localStorage.removeItem(ROLE_KEY);
  }

  return { token, userId, role, isAdmin, avatarStyle, setAvatarStyle, login, register, logout };
});
