"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { ThemeColors } from "@/app/theme";
import { useAuth } from "./AuthProvider";
import Logo from "./Logo";

export default function Nav({
  colors,
  dark,
  onToggleDark,
}: {
  colors: ThemeColors;
  dark: boolean;
  onToggleDark: () => void;
}) {
  const { user, logout } = useAuth();
  const router = useRouter();

  function handleSignOut() {
    logout();
    router.push("/");
  }

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "20px 48px",
        background: colors.navBg,
        backdropFilter: "blur(6px)",
        position: "sticky",
        top: 0,
        zIndex: 10,
      }}
    >
      <Link href="/" style={{ display: "flex", alignItems: "center", gap: 10, textDecoration: "none" }}>
        <Logo colors={colors} />
        <span
          className="display"
          style={{ fontWeight: 800, fontSize: 22, color: colors.textPrimary }}
        >
          BrickForgerAI
        </span>
      </Link>
      <div
        className="nav-links"
        style={{
          display: "flex",
          alignItems: "center",
          gap: 32,
          fontWeight: 600,
          color: colors.textPrimary,
          fontSize: 16,
        }}
      >
        <Link href="/" style={{ textDecoration: "none", color: "inherit" }}>Home</Link>
        <Link href="/discover" style={{ textDecoration: "none", color: "inherit" }}>Discover</Link>
        <Link href="/gallery" style={{ textDecoration: "none", color: "inherit" }}>My Builds</Link>
        <Link href="/pricing" style={{ textDecoration: "none", color: "inherit" }}>Pricing</Link>

        {user ? (
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <span
              title={user.email}
              style={{
                background: colors.badgeBg,
                color: colors.accent,
                fontSize: 13,
                fontWeight: 700,
                padding: "6px 12px",
                borderRadius: 20,
                whiteSpace: "nowrap",
              }}
            >
              {user.credits_remaining} credit{user.credits_remaining === 1 ? "" : "s"}
            </span>
            <button
              onClick={handleSignOut}
              style={{
                background: "none",
                border: "none",
                color: colors.textSecondary,
                fontSize: 15,
                fontWeight: 600,
                cursor: "pointer",
                fontFamily: "inherit",
                padding: 0,
              }}
            >
              Sign out
            </button>
          </div>
        ) : (
          <Link
            href="/signin"
            style={{
              textDecoration: "none",
              background: colors.accent,
              color: "#fff",
              padding: "8px 18px",
              borderRadius: 10,
              fontSize: 14,
              fontWeight: 700,
            }}
          >
            Sign in
          </Link>
        )}

        <div
          onClick={onToggleDark}
          role="button"
          aria-label="Toggle dark mode"
          style={{
            cursor: "pointer",
            width: 44,
            height: 24,
            borderRadius: 12,
            background: colors.toggleBg,
            position: "relative",
            transition: "background 0.3s",
            flexShrink: 0,
          }}
        >
          <div
            style={{
              position: "absolute",
              top: 2,
              left: dark ? 22 : 2,
              width: 20,
              height: 20,
              borderRadius: "50%",
              background: colors.accent,
              transition: "left 0.3s",
            }}
          />
        </div>
      </div>
    </div>
  );
}
