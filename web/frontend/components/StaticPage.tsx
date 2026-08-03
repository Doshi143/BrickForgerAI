"use client";

import { createContext, useContext } from "react";

import Nav from "@/components/Nav";
import Scenery from "@/components/Scenery";
import { useTheme } from "@/components/ThemeProvider";
import { ThemeColors, darkColors, lightColors } from "@/app/theme";

const PageColorContext = createContext<ThemeColors | null>(null);

export function usePageColors(): ThemeColors {
  const ctx = useContext(PageColorContext);
  if (!ctx) throw new Error("usePageColors must be used within StaticPage");
  return ctx;
}

/** Shared shell for simple content pages (How it Works, Help Center,
 * Terms, Privacy) -- same nav/scenery/card chrome as every other page,
 * just a prose column instead of app-specific UI. */
export default function StaticPage({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  const { dark, toggleDark } = useTheme();
  const colors = dark ? darkColors : lightColors;

  return (
    <div style={{ position: "relative", minHeight: "100vh", background: colors.skyBottom, overflowX: "hidden" }}>
      <Scenery colors={colors} dark={dark} prominence={0.35} />
      <div style={{ position: "relative", zIndex: 2 }}>
        <Nav colors={colors} dark={dark} onToggleDark={toggleDark} />

        <div style={{ maxWidth: 760, margin: "0 auto", padding: "56px 24px 100px" }}>
          <h1 className="display" style={{ fontWeight: 800, fontSize: 36, color: colors.textPrimary, margin: "0 0 8px" }}>
            {title}
          </h1>
          {subtitle && (
            <p style={{ color: colors.textSecondary, fontSize: 16, marginBottom: 36 }}>{subtitle}</p>
          )}

          <div
            style={{
              background: colors.cardBg,
              border: `1px solid ${colors.cardBorder}`,
              borderRadius: 20,
              padding: 40,
              color: colors.textPrimary,
              lineHeight: 1.7,
              fontSize: 15.5,
            }}
          >
            <PageColorContext.Provider value={colors}>{children}</PageColorContext.Provider>
          </div>
        </div>
      </div>
    </div>
  );
}

export function Section({ title, children }: { title: string; children: React.ReactNode }) {
  const colors = usePageColors();
  return (
    <div style={{ marginBottom: 28 }}>
      <h2 className="display" style={{ fontWeight: 700, fontSize: 19, color: colors.textPrimary, margin: "0 0 10px" }}>
        {title}
      </h2>
      <div style={{ color: colors.textSecondary }}>{children}</div>
    </div>
  );
}
