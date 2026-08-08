"use client";

import { createContext, useContext, useEffect, useState } from "react";

import { AuthUser, fetchMe, login as apiLogin, signup as apiSignup } from "@/lib/api";
import { getStoredSignupSource } from "@/components/ReferralCapture";

const STORAGE_KEY = "brickforgerai-token";

type AuthContextValue = {
  user: AuthUser | null;
  token: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export default function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  // Runs once on mount -- a stored token from a previous visit is
  // revalidated against the backend rather than trusted blindly, since it
  // may have expired or the account may no longer exist.
  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (!stored) {
      setLoading(false);
      return;
    }
    fetchMe(stored)
      .then((u) => {
        setToken(stored);
        setUser(u);
      })
      .catch(() => {
        window.localStorage.removeItem(STORAGE_KEY);
      })
      .finally(() => setLoading(false));
  }, []);

  function _apply(t: string, u: AuthUser) {
    window.localStorage.setItem(STORAGE_KEY, t);
    setToken(t);
    setUser(u);
  }

  async function login(email: string, password: string) {
    const { token: t, user: u } = await apiLogin(email, password);
    _apply(t, u);
  }

  async function signup(email: string, password: string) {
    const { token: t, user: u } = await apiSignup(email, password, getStoredSignupSource() ?? undefined);
    _apply(t, u);
  }

  function logout() {
    window.localStorage.removeItem(STORAGE_KEY);
    setToken(null);
    setUser(null);
  }

  async function refreshUser() {
    if (!token) return;
    const u = await fetchMe(token);
    setUser(u);
  }

  return (
    <AuthContext.Provider value={{ user, token, loading, login, signup, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (ctx === null) {
    throw new Error("useAuth must be used within <AuthProvider>");
  }
  return ctx;
}
