"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ThemeColors } from "@/app/theme";
import { useAuth } from "./AuthProvider";
import Logo from "./Logo";

const NAV_LINKS = [
  { href: "/", label: "Home" },
  { href: "/discover", label: "Discover" },
  { href: "/gallery", label: "My Builds" },
  { href: "/pricing", label: "Pricing" },
];

function DarkModeToggle({ colors, dark, onToggleDark }: { colors: ThemeColors; dark: boolean; onToggleDark: () => void }) {
  return (
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
  );
}

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
  const [menuOpen, setMenuOpen] = useState(false);

  function handleSignOut() {
    setMenuOpen(false);
    logout();
    router.push("/");
  }

  const authControl = user ? (
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
      onClick={() => setMenuOpen(false)}
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
  );

  return (
    <div
      style={{
        position: "sticky",
        top: 0,
        zIndex: 10,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "20px 48px",
          background: colors.navBg,
          backdropFilter: "blur(6px)",
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
          {NAV_LINKS.map((link) => (
            <Link key={link.href} href={link.href} style={{ textDecoration: "none", color: "inherit" }}>
              {link.label}
            </Link>
          ))}
          {authControl}
          <DarkModeToggle colors={colors} dark={dark} onToggleDark={onToggleDark} />
        </div>

        <button
          className="nav-menu-toggle"
          onClick={() => setMenuOpen((o) => !o)}
          aria-label={menuOpen ? "Close menu" : "Open menu"}
          aria-expanded={menuOpen}
          style={{
            background: "none",
            border: "none",
            cursor: "pointer",
            padding: 6,
            flexDirection: "column",
            justifyContent: "center",
            gap: 5,
            width: 32,
            height: 32,
          }}
        >
          <span
            style={{
              display: "block",
              width: 22,
              height: 2,
              borderRadius: 2,
              background: colors.textPrimary,
              transition: "transform 0.2s, opacity 0.2s",
              transform: menuOpen ? "translateY(7px) rotate(45deg)" : "none",
            }}
          />
          <span
            style={{
              display: "block",
              width: 22,
              height: 2,
              borderRadius: 2,
              background: colors.textPrimary,
              opacity: menuOpen ? 0 : 1,
              transition: "opacity 0.2s",
            }}
          />
          <span
            style={{
              display: "block",
              width: 22,
              height: 2,
              borderRadius: 2,
              background: colors.textPrimary,
              transition: "transform 0.2s, opacity 0.2s",
              transform: menuOpen ? "translateY(-7px) rotate(-45deg)" : "none",
            }}
          />
        </button>
      </div>

      {menuOpen && (
        <div
          className="nav-mobile-panel"
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 4,
            padding: "8px 24px 20px",
            background: colors.navBg,
            backdropFilter: "blur(6px)",
            borderTop: `1px solid ${colors.cardBorder}`,
          }}
        >
          {NAV_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              onClick={() => setMenuOpen(false)}
              style={{
                textDecoration: "none",
                color: colors.textPrimary,
                fontWeight: 600,
                fontSize: 16,
                padding: "12px 4px",
                borderBottom: `1px solid ${colors.cardBorder}`,
              }}
            >
              {link.label}
            </Link>
          ))}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "14px 4px 4px",
            }}
          >
            {authControl}
            <DarkModeToggle colors={colors} dark={dark} onToggleDark={onToggleDark} />
          </div>
        </div>
      )}
    </div>
  );
}
