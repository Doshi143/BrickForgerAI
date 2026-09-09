"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ThemeColors, USE_GLASSMORPHISM, USE_IMAGE_SCENERY, glassBlurStyle } from "@/app/theme";
import { useAuth } from "./AuthProvider";
import { useTheme } from "./ThemeProvider";
import Logo from "./Logo";

const NAV_LINKS = [
  { href: "/", label: "Home" },
  { href: "/discover", label: "Discover" },
  { href: "/gallery", label: "My Builds" },
  { href: "/pricing", label: "Pricing" },
];

// Feather-style icon glyphs drawn inline (no icon package dependency) --
// sized to fit inside the 20px knob. Sun uses a stroked circle + rays so it
// reads distinctly from the moon's solid crescent at this size.
function SunIcon({ size = 13 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="5" />
      <line x1="12" y1="1" x2="12" y2="3" />
      <line x1="12" y1="21" x2="12" y2="23" />
      <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
      <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
      <line x1="1" y1="12" x2="3" y2="12" />
      <line x1="21" y1="12" x2="23" y2="12" />
      <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
      <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
    </svg>
  );
}

function MoonIcon({ size = 13 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="#fff" stroke="none">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
    </svg>
  );
}

// 3 knob positions (day/evening/night) while USE_IMAGE_SCENERY is on, same
// 2-position day/night track otherwise -- reads `sceneryTime` from context
// directly rather than as a prop so both call sites below (desktop +
// mobile menu) pick this up for free with no prop-drilling changes.
function DarkModeToggle({ colors, dark, onToggleDark }: { colors: ThemeColors; dark: boolean; onToggleDark: () => void }) {
  const { sceneryTime } = useTheme();
  const trackWidth = USE_IMAGE_SCENERY ? 60 : 44;
  const knobLeft = USE_IMAGE_SCENERY
    ? { day: 2, evening: 20, night: 38 }[sceneryTime]
    : dark
    ? 22
    : 2;
  const knobIcon = USE_IMAGE_SCENERY ? (
    sceneryTime === "day" ? (
      <SunIcon size={13} />
    ) : sceneryTime === "night" ? (
      <MoonIcon size={13} />
    ) : (
      // Evening: both sun and moon together, shrunk to share the knob.
      <>
        <SunIcon size={8} />
        <MoonIcon size={8} />
      </>
    )
  ) : dark ? (
    <MoonIcon size={13} />
  ) : (
    <SunIcon size={13} />
  );
  return (
    <div
      onClick={onToggleDark}
      role="button"
      aria-label={USE_IMAGE_SCENERY ? "Cycle day / evening / night scenery" : "Toggle dark mode"}
      style={{
        cursor: "pointer",
        width: trackWidth,
        height: 24,
        borderRadius: 12,
        background: colors.toggleBg,
        position: "relative",
        transition: "background 0.3s, width 0.3s",
        flexShrink: 0,
      }}
    >
      <div
        style={{
          position: "absolute",
          top: 2,
          left: knobLeft,
          width: 20,
          height: 20,
          borderRadius: "50%",
          background: colors.accent,
          transition: "left 0.3s",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          gap: 1,
        }}
      >
        {knobIcon}
      </div>
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
          ...glassBlurStyle,
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
          position: "relative",
        }}
      >
        <Link href="/" style={{ display: "flex", alignItems: "center", gap: 6, textDecoration: "none" }}>
          <Logo size={31} />
          <span
            className="display"
            // The wordmark keeps its original logo font (Poppins) even
            // though .display switched to Roboto site-wide -- an inline
            // override here wins over that shared class rule.
            style={{ fontWeight: 800, fontSize: 22, color: colors.textPrimary, fontFamily: "'Poppins', sans-serif" }}
          >
            BrickForgerAI
          </span>
        </Link>

        {/* Centered independently of the logo/right-side widths via absolute
            positioning against the row's own relative container -- a plain
            flex layout can't true-center a middle group when its neighbors
            are different widths on each side. */}
        <div
          className="nav-links"
          style={{
            position: "absolute",
            left: "50%",
            transform: "translateX(-50%)",
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
        </div>

        <div className="nav-links" style={{ display: "flex", alignItems: "center", gap: 20 }}>
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
            // Same glass-card tokens/blur as the rest of the site when the
            // flag is on; flag off reproduces the dropdown's own original
            // navBg + 6px blur exactly (that pairing predates the
            // glassmorphism feature and isn't part of what it reverts).
            background: USE_GLASSMORPHISM ? colors.cardBg : colors.navBg,
            borderTop: `1px solid ${colors.cardBorder}`,
            ...(USE_GLASSMORPHISM
              ? glassBlurStyle
              : { backdropFilter: "blur(6px)", WebkitBackdropFilter: "blur(6px)" }),
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
