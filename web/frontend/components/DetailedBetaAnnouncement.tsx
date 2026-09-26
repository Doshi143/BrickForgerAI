"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { useTheme } from "@/components/ThemeProvider";
import { darkColors, lightColors } from "@/app/theme";
import { CREDIT_COST, MAINTENANCE_MODE, fetchFeatures } from "@/lib/api";

/** One-time popup announcing the Detailed beta, shown once per browser --
 * to new and returning visitors alike -- and only where the backend says
 * Detailed is on for this visitor (see fetchFeatures), so it can never
 * announce a mode the visitor can't pick.  Bump the key to announce again. */
const SEEN_KEY = "brickforge_seen_detailed_beta_v1";
// Don't interrupt signing in, signing up or resetting a password; it shows
// on the next page instead.
const SKIP_PATHS = ["/signin", "/signup", "/forgot-password", "/reset-password"];
export const SET_MODE_EVENT = "brickforge:set-mode";

function seen(): boolean {
  try {
    return window.localStorage.getItem(SEEN_KEY) !== null;
  } catch {
    return true; // storage blocked: we couldn't remember a dismissal, so never nag
  }
}

function markSeen() {
  try {
    window.localStorage.setItem(SEEN_KEY, new Date().toISOString());
  } catch {
    // not remembered; nothing else to do
  }
}

const POINTS = [
  "Best on buildings, vehicles and animals. Very thin or flat subjects are still hard for it.",
  `Uses ${CREDIT_COST.detailed} credits a build. If a build can't be made to hold together, both credits are refunded automatically.`,
  "Pick a smooth tiled finish or studs showing, and how much sideways building (studs not on top) to use.",
  "Every model still comes with the .ldr file, the full parts list and a step-by-step PDF build guide.",
];

export default function DetailedBetaAnnouncement() {
  const pathname = usePathname();
  const router = useRouter();
  const { dark } = useTheme();
  const { token, loading } = useAuth();
  const [open, setOpen] = useState(false);
  const primary = useRef<HTMLButtonElement>(null);

  function close() {
    markSeen();
    setOpen(false);
  }

  function tryIt() {
    close();
    try {
      window.localStorage.setItem("brickforge_mode", "detailed");
    } catch {
      // the home page falls back to its default mode
    }
    if (pathname === "/") window.dispatchEvent(new CustomEvent(SET_MODE_EVENT, { detail: "detailed" }));
    else router.push("/");
  }

  useEffect(() => {
    if (MAINTENANCE_MODE || loading || SKIP_PATHS.some((p) => pathname.startsWith(p)) || seen()) return;
    let cancelled = false;
    fetchFeatures(token).then((f) => {
      if (!cancelled && f.detailed_mode && !seen()) setOpen(true);
    });
    return () => {
      cancelled = true;
    };
  }, [pathname, token, loading]);

  useEffect(() => {
    if (!open) return;
    primary.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  if (!open) return null;

  const colors = dark ? darkColors : lightColors;

  return (
    <div
      onClick={close}
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 100,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 16,
        background: "rgba(5, 8, 20, 0.55)",
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="detailed-beta-title"
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "100%",
          maxWidth: 480,
          maxHeight: "calc(100vh - 32px)",
          overflowY: "auto",
          padding: "26px 26px 22px",
          borderRadius: 20,
          border: `1px solid ${colors.cardBorder}`,
          // the nav's frosted fill: cardBg's glass is too thin over the hero headline
          background: colors.navBg,
          color: colors.textPrimary,
          boxShadow: "0 20px 60px rgba(0,0,0,0.35)",
          textAlign: "left",
          backdropFilter: "blur(24px)",
          WebkitBackdropFilter: "blur(24px)",
        }}
      >
        <span
          style={{
            display: "inline-block",
            padding: "4px 12px",
            borderRadius: 999,
            fontSize: 12,
            fontWeight: 700,
            letterSpacing: 0.4,
            color: colors.accent,
            background: colors.badgeBg,
          }}
        >
          NEW - BETA
        </span>
        <h2 id="detailed-beta-title" style={{ margin: "14px 0 10px", fontSize: 24, fontWeight: 800 }}>
          Detailed mode is now live
        </h2>
        <p style={{ margin: 0, fontSize: 15, lineHeight: 1.55, color: colors.textSecondary }}>
          A second way to generate. Instead of sculpting your model from a generated 3D shape, Detailed
          designs it piece by piece with real building techniques - curved slopes, round bricks, windows,
          doors, real wheels, plants and sideways building.
        </p>
        <ul style={{ margin: "16px 0 0", paddingLeft: 20, fontSize: 14, lineHeight: 1.55, color: colors.textSecondary }}>
          {POINTS.map((p) => (
            <li key={p} style={{ marginBottom: 6 }}>
              {p}
            </li>
          ))}
        </ul>
        <p style={{ margin: "10px 0 0", fontSize: 13, lineHeight: 1.5, color: colors.textSecondary, opacity: 0.85 }}>
          It&apos;s a beta, so results will vary. Voxel mode is still there and still uses {CREDIT_COST.voxel} credit.
          Switch between them under the prompt box.
        </p>
        <div style={{ display: "flex", gap: 10, marginTop: 22, flexWrap: "wrap" }}>
          <button
            ref={primary}
            onClick={tryIt}
            style={{
              flex: "1 1 160px",
              background: colors.accent,
              color: "#fff",
              border: "none",
              padding: "13px 20px",
              borderRadius: 12,
              fontWeight: 700,
              fontSize: 15,
              cursor: "pointer",
              fontFamily: "inherit",
            }}
          >
            Try Detailed
          </button>
          <button
            onClick={close}
            style={{
              flex: "1 1 120px",
              background: "transparent",
              color: colors.textPrimary,
              border: `1px solid ${colors.cardBorder}`,
              padding: "13px 20px",
              borderRadius: 12,
              fontWeight: 600,
              fontSize: 15,
              cursor: "pointer",
              fontFamily: "inherit",
            }}
          >
            Maybe later
          </button>
        </div>
      </div>
    </div>
  );
}
