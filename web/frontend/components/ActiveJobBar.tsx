"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useActiveJob } from "@/components/ActiveJobProvider";
import { useTheme } from "@/components/ThemeProvider";
import { darkColors, lightColors } from "@/app/theme";
import { STATUS_LABELS } from "@/lib/api";

/** Floating bar, visible from anywhere in the app, showing progress (or
 * the finished/failed result) of the most recently started generation --
 * see ActiveJobProvider for why this exists. Hidden on the job's own
 * results page, since that page already shows the same information in
 * full and auto-clears the tracker once it's seen the terminal state
 * (see that page's own effect). */
export default function ActiveJobBar() {
  const pathname = usePathname();
  const { dark } = useTheme();
  const { activeJob, activeJobId, dismiss } = useActiveJob();

  if (!activeJobId || !activeJob) return null;
  if (pathname === `/generate/${activeJobId}`) return null;

  const colors = dark ? darkColors : lightColors;
  const done = activeJob.status === "done";
  const failed = activeJob.status === "failed";

  return (
    <div
      style={{
        position: "fixed",
        left: "50%",
        bottom: 20,
        transform: "translateX(-50%)",
        zIndex: 50,
        display: "flex",
        alignItems: "center",
        gap: 14,
        background: colors.cardBg,
        border: `1px solid ${colors.cardBorder}`,
        borderRadius: 16,
        padding: "12px 16px 12px 18px",
        boxShadow: "0 8px 30px rgba(0,0,0,0.25)",
        maxWidth: "calc(100vw - 32px)",
      }}
    >
      {!done && !failed && (
        <div
          style={{
            width: 16,
            height: 16,
            border: `2.5px solid ${colors.accent}`,
            borderTopColor: "transparent",
            borderRadius: "50%",
            animation: "spin 0.9s linear infinite",
            flexShrink: 0,
          }}
        />
      )}
      {done && <span style={{ fontSize: 16, flexShrink: 0 }}>✓</span>}
      {failed && <span style={{ fontSize: 16, flexShrink: 0 }}>⚠</span>}

      <div style={{ minWidth: 0 }}>
        <div
          style={{
            color: colors.textPrimary,
            fontWeight: 700,
            fontSize: 14,
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {failed ? "Generation failed" : done ? "Your model is ready" : STATUS_LABELS[activeJob.status]}
        </div>
        <div
          style={{
            color: colors.textSecondary,
            fontSize: 12,
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
            maxWidth: 220,
          }}
        >
          {activeJob.prompt}
        </div>
      </div>

      <Link
        href={`/generate/${activeJobId}`}
        style={{
          color: colors.accent,
          fontWeight: 700,
          fontSize: 13,
          textDecoration: "none",
          whiteSpace: "nowrap",
          marginLeft: 4,
        }}
      >
        {done ? "View →" : failed ? "Details →" : "View progress →"}
      </Link>

      <button
        onClick={dismiss}
        aria-label="Dismiss"
        style={{
          background: "none",
          border: "none",
          color: colors.textSecondary,
          cursor: "pointer",
          fontSize: 16,
          padding: 0,
          marginLeft: 4,
          lineHeight: 1,
        }}
      >
        ×
      </button>
    </div>
  );
}
