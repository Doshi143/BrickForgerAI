"use client";

import { useState } from "react";

import { ApiError, joinWaitlist } from "@/lib/api";
import { ThemeColors } from "@/app/theme";

/** Shown on the homepage instead of the real generate flow whenever
 * MAINTENANCE_MODE is on (see lib/api.ts) -- the one thing a visitor can
 * still do is leave an email for when generation reopens. Deliberately its
 * own component, not inlined into page.tsx: MAINTENANCE_MODE is meant to
 * be flipped on and back off again, and keeping this self-contained means
 * removing it later is a one-line revert in page.tsx, not untangling
 * mixed state out of the main page component. */
export default function WaitlistForm({ colors }: { colors: ThemeColors }) {
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit() {
    const trimmed = email.trim();
    if (!trimmed || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      await joinWaitlist(trimmed);
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong -- please try again.");
      setSubmitting(false);
    }
  }

  if (done) {
    return (
      <div
        style={{
          marginTop: 40,
          maxWidth: 560,
          marginLeft: "auto",
          marginRight: "auto",
          padding: "20px 24px",
          borderRadius: 14,
          border: `1px solid ${colors.cardBorder}`,
          background: colors.cardBg,
        }}
      >
        <p style={{ color: colors.textPrimary, fontSize: 16, fontWeight: 600, margin: 0 }}>
          You&apos;re on the list!
        </p>
        <p style={{ color: colors.textSecondary, fontSize: 14, marginTop: 8, marginBottom: 0 }}>
          We&apos;ll email you the moment generations reopen.
        </p>
      </div>
    );
  }

  return (
    <div style={{ marginTop: 40, maxWidth: 560, marginLeft: "auto", marginRight: "auto" }}>
      <div
        style={{
          padding: "20px 24px",
          borderRadius: 14,
          border: `1px solid ${colors.cardBorder}`,
          background: colors.cardBg,
        }}
      >
        <p style={{ color: colors.textPrimary, fontSize: 17, fontWeight: 700, margin: 0 }}>
          Generation is temporarily paused
        </p>
        <p style={{ color: colors.textSecondary, fontSize: 14, marginTop: 8, marginBottom: 18 }}>
          We&apos;re taking a short break while we restock our AI budget. Leave your email and
          we&apos;ll let you know the moment it&apos;s back.
        </p>
        <div className="prompt-row" style={{ display: "flex", gap: 10 }}>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
            disabled={submitting}
            placeholder="you@example.com"
            style={{
              flex: 1,
              padding: "14px 16px",
              borderRadius: 12,
              border: `1px solid ${colors.inputBorder}`,
              background: colors.skyBottom,
              color: colors.textPrimary,
              fontSize: 15,
              outline: "none",
              fontFamily: "inherit",
            }}
          />
          <button
            onClick={handleSubmit}
            disabled={submitting || !email.trim()}
            style={{
              background: colors.accent,
              color: "#fff",
              border: "none",
              padding: "14px 24px",
              borderRadius: 12,
              fontWeight: 700,
              fontSize: 15,
              cursor: "pointer",
              fontFamily: "inherit",
              whiteSpace: "nowrap",
            }}
          >
            {submitting ? "Joining…" : "Notify me"}
          </button>
        </div>
        {error && (
          <p style={{ color: "#ff8f6b", marginTop: 14, marginBottom: 0, fontSize: 14 }}>{error}</p>
        )}
      </div>
    </div>
  );
}
