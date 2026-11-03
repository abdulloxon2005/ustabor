import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import * as SecureStore from "expo-secure-store";
import { authApi } from "../api";
import { ApiError, setAuthToken, setUnauthorizedHandler } from "../api/client";
import type { TokenOut, User } from "../api/types";

const TOKEN_KEY = "ustabor_customer_token";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (phone: string, password: string) => Promise<void>;
  completeAuth: (t: TokenOut) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

async function saveToken(token: string | null) {
  try {
    if (token) await SecureStore.setItemAsync(TOKEN_KEY, token);
    else await SecureStore.deleteItemAsync(TOKEN_KEY);
  } catch {
    /* SecureStore mavjud bo'lmagan muhit (web) — sessiya xotirada qoladi */
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const logout = useCallback(async () => {
    setAuthToken(null);
    setUser(null);
    await saveToken(null);
  }, []);

  // Ilova ochilganda saqlangan tokenni tekshirish
  useEffect(() => {
    setUnauthorizedHandler(() => {
      void logout();
    });
    (async () => {
      try {
        const token = await SecureStore.getItemAsync(TOKEN_KEY);
        if (token) {
          setAuthToken(token);
          const me = await authApi.me();
          if (me.role === "customer") setUser(me);
          else await logout();
        }
      } catch (e) {
        // Tarmoq xatosida tokenni saqlab qolamiz, faqat 401 da chiqamiz
        if (e instanceof ApiError && e.status === 401) await logout();
      } finally {
        setLoading(false);
      }
    })();
    return () => setUnauthorizedHandler(null);
  }, [logout]);

  const completeAuth = useCallback(async (t: TokenOut) => {
    if (t.user.role !== "customer") {
      throw new ApiError("Bu ilova faqat mijozlar uchun. Ustalar alohida ilovadan foydalanadi.", 403);
    }
    setAuthToken(t.access_token);
    await saveToken(t.access_token);
    setUser(t.user);
  }, []);

  const login = useCallback(
    async (phone: string, password: string) => {
      const t = await authApi.login(phone, password);
      await completeAuth(t);
    },
    [completeAuth]
  );

  const value = useMemo(
    () => ({ user, loading, login, completeAuth, logout }),
    [user, loading, login, completeAuth, logout]
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth AuthProvider ichida ishlatilishi kerak");
  return ctx;
}
