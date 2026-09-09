"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { USE_IMAGE_SCENERY } from "@/app/theme";

const LEGACY_STORAGE_KEY = "brickforgerai-dark-mode";
const STORAGE_KEY = "brickforgerai-scenery-time";

export type SceneryTime = "day" | "evening" | "night";

type ThemeContextValue = {
  dark: boolean;
  toggleDark: () => void;
  /** "day" | "evening" | "night" -- only meaningful while USE_IMAGE_SCENERY
   * is on (see app/theme.ts). Exposed unconditionally anyway so a consumer
   * never has to branch on the flag itself -- `dark` alone still drives
   * every existing light/dark color choice untouched either way. */
  sceneryTime: SceneryTime;
};

// Landing page and the results page each used to hold their own `useState`
// for dark/light, so navigating from one to the other reset the theme to
// whatever that page's own default happened to be -- this context is the
// fix: one value, read/written from localStorage, shared across every
// route via the root layout.
const ThemeContext = createContext<ThemeContextValue | null>(null);

function initialSceneryTime(): SceneryTime {
  if (typeof window === "undefined") return "evening";
  const stored = window.localStorage.getItem(STORAGE_KEY);
  if (stored === "day" || stored === "evening" || stored === "night") return stored;
  // No new-key preference yet -- a returning visitor's OLD boolean choice
  // (light/dark) is honored as the closest match (dark -> night, light ->
  // day) rather than silently reset to the new "evening" default; only a
  // genuinely first-time visitor (neither key present) gets "evening".
  const legacy = window.localStorage.getItem(LEGACY_STORAGE_KEY);
  if (legacy === "true") return "night";
  if (legacy === "false") return "day";
  return "evening";
}

export default function ThemeProvider({ children }: { children: React.ReactNode }) {
  // Lazy initializer runs once, synchronously, before first paint -- avoids
  // a flash of the wrong theme that a useEffect-based read would cause.
  const [sceneryTime, setSceneryTime] = useState<SceneryTime>(() =>
    USE_IMAGE_SCENERY ? initialSceneryTime() : "evening"
  );
  // Byte-identical fallback for the flag-off revert path: a real, independent
  // boolean rather than deriving "false" (=light) from sceneryTime for every
  // page that isn't "night" -- USE_IMAGE_SCENERY off must reproduce the
  // exact original 2-state light/dark behavior, defaults included, not a
  // hybrid of the two schemes.
  const [legacyDark, setLegacyDark] = useState<boolean>(() => {
    if (USE_IMAGE_SCENERY) return false; // unused in this mode
    if (typeof window === "undefined") return false;
    const stored = window.localStorage.getItem(LEGACY_STORAGE_KEY);
    return stored === null ? false : stored === "true";
  });

  useEffect(() => {
    if (USE_IMAGE_SCENERY) {
      window.localStorage.setItem(STORAGE_KEY, sceneryTime);
    } else {
      window.localStorage.setItem(LEGACY_STORAGE_KEY, String(legacyDark));
    }
  }, [sceneryTime, legacyDark]);

  const dark = USE_IMAGE_SCENERY ? sceneryTime === "night" : legacyDark;

  function toggleDark() {
    if (USE_IMAGE_SCENERY) {
      setSceneryTime((t) => (t === "day" ? "evening" : t === "evening" ? "night" : "day"));
    } else {
      setLegacyDark((d) => !d);
    }
  }

  return (
    <ThemeContext.Provider value={{ dark, toggleDark, sceneryTime }}>{children}</ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (ctx === null) {
    throw new Error("useTheme must be used within <ThemeProvider>");
  }
  return ctx;
}
