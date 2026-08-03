"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import Nav from "@/components/Nav";
import Scenery from "@/components/Scenery";
import { useAuth } from "@/components/AuthProvider";
import { useTheme } from "@/components/ThemeProvider";
import { ThemeColors, darkColors, lightColors } from "@/app/theme";
import { ApiError } from "@/lib/api";

export default function AuthForm({ mode }: { mode: "signin" | "signup" }) {
  const { dark, toggleDark } = useTheme();
  const { login, signup } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const colors = dark ? darkColors : lightColors;
  const isSignup = mode === "signup";

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      if (isSignup) {
        await signup(email, password);
      } else {
        await login(email, password);
      }
      router.push(searchParams.get("next") ?? "/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong");
      setSubmitting(false);
    }
  }

  return (
    <div style={{ position: "relative", minHeight: "100vh", background: colors.skyBottom, overflowX: "hidden" }}>
      <Scenery colors={colors} dark={dark} prominence={0.35} />
      <div style={{ position: "relative", zIndex: 2 }}>
        <Nav colors={colors} dark={dark} onToggleDark={toggleDark} />

        <div style={{ maxWidth: 420, margin: "0 auto", padding: "64px 24px 100px" }}>
          <div
            style={{
              background: colors.cardBg,
              border: `1px solid ${colors.cardBorder}`,
              borderRadius: 20,
              padding: 36,
            }}
          >
            <h1 className="display" style={{ fontWeight: 800, fontSize: 26, color: colors.textPrimary, margin: "0 0 8px" }}>
              {isSignup ? "Create your account" : "Welcome back"}
            </h1>
            <p style={{ color: colors.textSecondary, fontSize: 14, marginBottom: 28 }}>
              {isSignup
                ? "Free plan includes 10 build credits a month."
                : "Sign in to keep building."}
            </p>

            <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <span style={{ fontSize: 13, fontWeight: 600, color: colors.textSecondary }}>Email</span>
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  style={inputStyle(colors)}
                />
              </label>
              <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <span style={{ fontSize: 13, fontWeight: 600, color: colors.textSecondary }}>Password</span>
                <input
                  type="password"
                  required
                  minLength={8}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  style={inputStyle(colors)}
                />
                {isSignup && (
                  <span style={{ fontSize: 12, color: colors.textSecondary }}>At least 8 characters.</span>
                )}
              </label>

              {error && <p style={{ color: "#ff8f6b", fontSize: 14, margin: 0 }}>{error}</p>}

              <button
                type="submit"
                disabled={submitting}
                style={{
                  marginTop: 8,
                  background: colors.accent,
                  color: "#fff",
                  border: "none",
                  padding: "14px 20px",
                  borderRadius: 12,
                  fontWeight: 700,
                  fontSize: 15,
                  cursor: "pointer",
                  fontFamily: "inherit",
                }}
              >
                {submitting ? "Please wait…" : isSignup ? "Create account" : "Sign in"}
              </button>
            </form>

            <p style={{ color: colors.textSecondary, fontSize: 14, marginTop: 24, textAlign: "center" }}>
              {isSignup ? (
                <>
                  Already have an account?{" "}
                  <Link href="/signin" style={{ color: colors.accent, fontWeight: 700, textDecoration: "none" }}>
                    Sign in
                  </Link>
                </>
              ) : (
                <>
                  New here?{" "}
                  <Link href="/signup" style={{ color: colors.accent, fontWeight: 700, textDecoration: "none" }}>
                    Create an account
                  </Link>
                </>
              )}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

function inputStyle(colors: ThemeColors): React.CSSProperties {
  return {
    padding: "12px 14px",
    borderRadius: 10,
    border: `1px solid ${colors.inputBorder}`,
    background: colors.skyBottom,
    color: colors.textPrimary,
    fontSize: 15,
    outline: "none",
    fontFamily: "inherit",
  };
}
