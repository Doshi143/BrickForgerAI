"use client";

import { createContext, useContext, useEffect, useState } from "react";

const STORAGE_KEY = "brickforgerai-dark-mode";

type ThemeContextValue = {
  dark: boolean;
  toggleDark: () => void;
};

// Landing page and the results page each used to hold their own `useState`
// for dark/light, so navigating from one to the other reset the theme to
// whatever that page's own default happened to be -- this context is the
// fix: one value, read/written from localStorage, shared across every
// route via the root layout.
const ThemeContext = createContext<ThemeContextValue | null>(null);

export default function ThemeProvider({ children }: { children: React.ReactNode }) {
  // Lazy initializer runs once, synchronously, before first paint -- avoids
  // a flash of the wrong theme that a useEffect-based read would cause.
  const [dark, setDark] = useState<boolean>(() => {
    if (typeof window === "undefined") return true;
    const stored = window.localStorage.getItem(STORAGE_KEY);
    return stored === null ? true : stored === "true";
  });

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, String(dark));
  }, [dark]);

  return (
    <ThemeContext.Provider value={{ dark, toggleDark: () => setDark((d) => !d) }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (ctx === null) {
    throw new Error("useTheme must be used within <ThemeProvider>");
  }
  return ctx;
}
