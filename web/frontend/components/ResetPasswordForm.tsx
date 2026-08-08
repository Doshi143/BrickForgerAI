"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import Nav from "@/components/Nav";
import Scenery from "@/components/Scenery";
import { useTheme } from "@/components/ThemeProvider";
import { darkColors, lightColors } from "@/app/theme";
import { ApiError, resetPassword } from "@/lib/api";
import { inputStyle } from "@/components/authFormStyles";

// Same useSearchParams()-needs-Suspense requirement as AuthForm.tsx (the
// token comes from the URL's query string) -- see that file's comment for
// the exact build failure this avoids.
export default function ResetPasswordForm() {
  return (
    <Suspense fallback={null}>
      <ResetPasswordFormInner />
    </Suspense>
  );
}

function ResetPasswordFormInner() {
  const { dark, toggleDark } = useTheme();
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";

  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const colors = dark ? darkColors : lightColors;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (submitting) return;
    if (password !== confirmPassword) {
      setError("Passwords don't match");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await resetPassword(token, password);
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong");
    } finally {
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
              Choose a new password
            </h1>

            {!token ? (
              <p style={{ color: colors.textSecondary, fontSize: 14, lineHeight: 1.5 }}>
                This link is missing its reset token. Request a new one from{" "}
                <Link href="/forgot-password" style={{ color: colors.accent, fontWeight: 700, textDecoration: "none" }}>
                  the forgot password page
                </Link>
                .
              </p>
            ) : done ? (
              <>
                <p style={{ color: colors.textSecondary, fontSize: 14, marginBottom: 20 }}>
                  Your password has been updated.
                </p>
                <button
                  onClick={() => router.push("/signin")}
                  style={{
                    background: colors.accent,
                    color: "#fff",
                    border: "none",
                    padding: "14px 20px",
                    borderRadius: 12,
                    fontWeight: 700,
                    fontSize: 15,
                    cursor: "pointer",
                    fontFamily: "inherit",
                    width: "100%",
                  }}
                >
                  Sign in
                </button>
              </>
            ) : (
              <>
                <p style={{ color: colors.textSecondary, fontSize: 14, marginBottom: 28 }}>
                  Enter a new password for your account.
                </p>
                <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                  <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    <span style={{ fontSize: 13, fontWeight: 600, color: colors.textSecondary }}>New password</span>
                    <input
                      type="password"
                      required
                      minLength={8}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      style={inputStyle(colors)}
                    />
                    <span style={{ fontSize: 12, color: colors.textSecondary }}>At least 8 characters.</span>
                  </label>
                  <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    <span style={{ fontSize: 13, fontWeight: 600, color: colors.textSecondary }}>Confirm password</span>
                    <input
                      type="password"
                      required
                      minLength={8}
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      style={inputStyle(colors)}
                    />
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
                    {submitting ? "Please wait…" : "Reset password"}
                  </button>
                </form>
              </>
            )}

            <p style={{ color: colors.textSecondary, fontSize: 14, marginTop: 24, textAlign: "center" }}>
              <Link href="/signin" style={{ color: colors.accent, fontWeight: 700, textDecoration: "none" }}>
                Back to sign in
              </Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
