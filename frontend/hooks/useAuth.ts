"use client";

import { useCallback, useEffect, useState } from "react";
import { apiRequest } from "@/lib/api/client";
import { clearAccessToken, getAccessToken, setAccessToken } from "@/lib/auth/token";
import type { TokenResponse, User } from "@/types";

export function useAuth() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const loadUser = useCallback(async () => {
    if (!getAccessToken()) {
      setLoading(false);
      return;
    }
    try {
      const me = await apiRequest<User>("/users/me");
      setUser(me);
    } catch {
      clearAccessToken();
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadUser();
  }, [loadUser]);

  const login = useCallback(async (email: string, password: string) => {
    const tokens = await apiRequest<TokenResponse>("/auth/login", {
      method: "POST",
      body: { email, password },
      auth: false,
    });
    setAccessToken(tokens.access_token);
    await loadUser();
  }, [loadUser]);

  const signup = useCallback(async (email: string, password: string, fullName?: string) => {
    const tokens = await apiRequest<TokenResponse>("/auth/signup", {
      method: "POST",
      body: { email, password, full_name: fullName },
      auth: false,
    });
    setAccessToken(tokens.access_token);
    await loadUser();
  }, [loadUser]);

  const logout = useCallback(() => {
    clearAccessToken();
    setUser(null);
  }, []);

  return { user, loading, login, signup, logout };
}
