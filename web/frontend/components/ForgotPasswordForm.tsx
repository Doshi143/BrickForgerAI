"use client";

import Link from "next/link";
import { useState } from "react";

import Nav from "@/components/Nav";
import Scenery from "@/components/Scenery";
import { useTheme } from "@/components/ThemeProvider";
import { darkColors, lightColors } from "@/app/theme";
import { forgotPassword } from "@/lib/api";
import { inputStyle } from "@/components/authFormStyles";

export default function ForgotPasswordForm() {
  const { dark, toggleDark } = useTheme();
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  // Set on any response, success or failure -- the backend returns the
  // same generic message either way (see lib/api.ts::forgotPassword), so
  // there's no separate error state to distinguish here.
  const [message, setMessage] = useState<string | null>(null);

  const colors = dark ? darkColors : lightColors;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    try {
      const res = await forgotPassword(email);
      setMessage(res.message);
    } catch {
      // Even a network/server error shouldn't reveal anything -- show the
      // same reassuring copy rather than a scary error state.
      setMessage("If an account exists for that email, we've sent password reset instructions.");
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
              Reset your password
            </h1>
            <p style={{ color: colors.textSecondary, fontSize: 14, marginBottom: 28 }}>
              Enter the email on your account and we&apos;ll send you a link to reset your password.
            </p>

            {message ? (
              <p style={{ color: colors.textPrimary, fontSize: 15, lineHeight: 1.5 }}>{message}</p>
            ) : (
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
                  {submitting ? "Sending…" : "Send reset link"}
                </button>
              </form>
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
