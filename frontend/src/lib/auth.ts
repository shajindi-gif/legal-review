import { create } from "zustand";
import type { User } from "@/types/api";

const TOKEN_KEY = "lr_token";
const USER_KEY = "lr_user";
const HINT_COOKIE = "lr_hint";

/**
 * 同步「登录提示」cookie（非凭证：仅值为 "1"，不含任何 token）。
 * 供 proxy.ts 路由层守卫读取；真正鉴权始终在后端 JWT。
 * 旧版曾把 access token 写入 cookie（lr_token），已废弃并在此清除。
 */
function syncHintCookie(loggedIn: boolean) {
  if (typeof document === "undefined") return;
  if (loggedIn) {
    document.cookie = `${HINT_COOKIE}=1; path=/; max-age=${60 * 60 * 24 * 30}; samesite=lax`;
  } else {
    document.cookie = `${HINT_COOKIE}=; path=/; max-age=0`;
    // 兼容清理：旧版本曾把 access token 落 cookie
    document.cookie = `${TOKEN_KEY}=; path=/; max-age=0`;
    document.cookie = `${TOKEN_KEY}=; path=/api/v1/auth; max-age=0`;
  }
}

interface AuthState {
  token: string | null;
  user: User | null;
  hydrated: boolean;
  setAuth: (token: string, user: User) => void;
  setUser: (user: User) => void;
  logout: () => void;
  hydrate: () => void;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  token: null,
  user: null,
  hydrated: false,
  setAuth: (token, user) => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(TOKEN_KEY, token);
      window.localStorage.setItem(USER_KEY, JSON.stringify(user));
      syncHintCookie(true);
    }
    set({ token, user });
  },
  setUser: (user) => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(USER_KEY, JSON.stringify(user));
    }
    set({ user });
  },
  logout: () => {
    if (typeof window !== "undefined") {
      window.localStorage.removeItem(TOKEN_KEY);
      window.localStorage.removeItem(USER_KEY);
      syncHintCookie(false);
    }
    set({ token: null, user: null });
  },
  hydrate: () => {
    if (typeof window === "undefined") return;
    if (get().hydrated) return;
    const token = window.localStorage.getItem(TOKEN_KEY);
    const raw = window.localStorage.getItem(USER_KEY);
    let user: User | null = null;
    if (raw) {
      try {
        user = JSON.parse(raw) as User;
      } catch {
        user = null;
      }
    }
    syncHintCookie(Boolean(token && user));
    set({ token, user, hydrated: true });
  },
}));
