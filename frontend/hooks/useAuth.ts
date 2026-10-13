"use client";
import {useCallback, useEffect, useState} from "react";
import {apiRequest} from "@/lib/api/client";
import type {User} from "@/types";

export function useAuth() {
  const [user, setUser] = useState<User|null>(null);
  const [loading, setLoading] = useState(true);
  const loadUser = useCallback(async () => {
    try { setUser(await apiRequest<User>("/users/me")); }
    catch { setUser(null); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => {
    // Phase 8's browser-accessible token is no longer used by the BFF.
    // Erase it on migration so old sessions cannot linger in localStorage.
    window.localStorage.removeItem("ai_video_platform_access_token");
    void loadUser();
  }, [loadUser]);
  const login = useCallback(async(email: string, password: string) => {
    await apiRequest("/auth/login", {method:"POST",body:{email,password},auth:false});
    await loadUser();
  }, [loadUser]);
  const signup = useCallback(async(email: string,password:string,fullName?:string) => {
    await apiRequest("/auth/signup", {method:"POST",body:{email,password,full_name:fullName},auth:false});
    await loadUser();
  },[loadUser]);
  const logout = useCallback(async() => {
    try { await apiRequest("/auth/logout", {method:"POST"}); }
    finally { setUser(null); window.location.replace("/login"); }
  }, []);
  return {user, loading, login, signup, logout};
}
