import { create } from "zustand";
import type { User } from "@/types/api";

const TOKEN_KEY = "lr_token";
const USER_KEY = "lr_user";

/** 在浏览器端把 token 同步写入 cookie，供 proxy.ts（路由层）读取做守卫。 */
function syncCookie(token: string | null) {
  if (typeof document === "undefined") return;
  if (token) {
    document.cookie = `${TOKEN_KEY}=${token}; path=/; max-age=${60 * 60 * 24 * 7}; samesite=lax`;
  } else {
    document.cookie = `${TOKEN_KEY}=; path=/; max-age=0`;
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
      syncCookie(token);
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
      syncCookie(null);
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
    syncCookie(token);
    set({ token, user, hydrated: true });
  },
}));
