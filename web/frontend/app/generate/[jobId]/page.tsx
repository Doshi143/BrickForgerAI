"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { use, useEffect, useState } from "react";

import Nav from "@/components/Nav";
import Scenery from "@/components/Scenery";
import { useAuth } from "@/components/AuthProvider";
import { useTheme } from "@/components/ThemeProvider";
import { ThemeColors, darkColors, lightColors } from "@/app/theme";
import {
  Job,
  STATUS_LABELS,
  STATUS_ORDER,
  downloadUrl,
  fetchJob,
  previewUrl,
  saveRender,
  unlockInstructions,
} from "@/lib/api";

// three.js touches `window` at import time, so it can never run during SSR.
const Viewer3D = dynamic(() => import("@/components/Viewer3D"), {
  ssr: false,
  loading: () => <div style={{ height: 520 }} />,
});

const POLL_INTERVAL_MS = 2000;

export default function GeneratePage({ params }: { params: Promise<{ jobId: string }> }) {
  const { jobId } = use(params);
  const { dark, toggleDark } = useTheme();
  const { token } = useAuth();
  const [job, setJob] = useState<Job | null>(null);
  const [pollError, setPollError] = useState<string | null>(null);
  const [unlocking, setUnlocking] = useState(false);

  async function handleUnlock() {
    if (!token || unlocking) return;
    setUnlocking(true);
    try {
      const updated = await unlockInstructions(jobId, token);
      setJob(updated);
    } finally {
      setUnlocking(false);
    }
  }

  const colors = dark ? darkColors : lightColors;

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;

    async function poll() {
      try {
        const next = await fetchJob(jobId);
        if (cancelled) return;
        setJob(next);
        setPollError(null);
        if (next.status !== "done" && next.status !== "failed") {
          timer = setTimeout(poll, POLL_INTERVAL_MS);
        }
      } catch (err) {
        if (cancelled) return;
        setPollError((err as Error).message);
        timer = setTimeout(poll, POLL_INTERVAL_MS);
      }
    }

    poll();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [jobId]);

  return (
    <div style={{ position: "relative", minHeight: "100vh", background: colors.skyBottom, overflowX: "hidden" }}>
      <Scenery colors={colors} dark={dark} prominence={0.35} />
      <div style={{ position: "relative", zIndex: 2 }}>
        <Nav colors={colors} dark={dark} onToggleDark={toggleDark} />

        <div style={{ maxWidth: 960, margin: "0 auto", padding: "48px 24px 100px" }}>
          <Link href="/" style={{ color: colors.textSecondary, fontSize: 15, textDecoration: "none" }}>
            ← Build another
          </Link>

          <h1 className="display" style={{ fontWeight: 800, fontSize: 34, color: colors.textPrimary, margin: "18px 0 6px" }}>
            {job?.prompt ?? "Loading…"}
          </h1>
          <div style={{ color: colors.textSecondary, fontSize: 14, marginBottom: 28 }}>Job {jobId}</div>

          {pollError && (
            <Card colors={colors}>
              <div style={{ color: "#ff8f6b" }}>
                Can&apos;t reach the backend ({pollError}). Retrying every {POLL_INTERVAL_MS / 1000}s…
              </div>
            </Card>
          )}

          {job && job.status !== "done" && job.status !== "failed" && (
            <Card colors={colors}>
              <ProgressTrack colors={colors} status={job.status} studs={job.target_size_studs} />
            </Card>
          )}

          {job?.status === "failed" && (
            <Card colors={colors}>
              <div className="display" style={{ fontWeight: 700, fontSize: 20, color: "#ff8f6b", marginBottom: 12 }}>
                Generation failed
              </div>
              <pre
                style={{
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                  fontSize: 13,
                  lineHeight: 1.5,
                  color: colors.textSecondary,
                  margin: 0,
                  maxHeight: 320,
                  overflow: "auto",
                }}
              >
                {job.error}
              </pre>
            </Card>
          )}

          {job?.status === "done" && job.ldr_download_url && (
            <>
              <Card colors={colors} padded={false}>
                <Viewer3D
                  src={previewUrl(jobId)}
                  onRendered={(dataUrl) => {
                    saveRender(jobId, dataUrl).catch(() => {
                      // Cosmetic only (gallery thumbnail) -- a failed
                      // upload just means the gallery falls back to the
                      // reference photo for this job, nothing breaks.
                    });
                  }}
                />
              </Card>

              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 16, marginTop: 24 }}>
                <Stat colors={colors} label="Parts" value={job.part_count?.toLocaleString() ?? "—"} />
                <Stat colors={colors} label="Colors" value={job.color_count?.toString() ?? "—"} />
                <Stat colors={colors} label="Slopes" value={job.slope_count?.toString() ?? "—"} />
                <Stat colors={colors} label="Tiles" value={job.tile_count?.toString() ?? "—"} />
                <Stat
                  colors={colors}
                  label="Structure"
                  value={job.is_single_piece ? "One piece" : "Split"}
                />
              </div>

              <div style={{ display: "flex", gap: 14, marginTop: 28, flexWrap: "wrap" }}>
                {job.instructions_unlocked ? (
                  <a
                    href={downloadUrl(jobId)}
                    download
                    style={{
                      background: colors.accent,
                      color: "#fff",
                      padding: "16px 28px",
                      borderRadius: 14,
                      fontWeight: 700,
                      fontSize: 16,
                      textDecoration: "none",
                    }}
                  >
                    Download .ldr ↓
                  </a>
                ) : (
                  <button
                    onClick={handleUnlock}
                    disabled={unlocking}
                    style={{
                      background: "none",
                      border: `2px solid ${colors.accent}`,
                      color: colors.accent,
                      padding: "14px 26px",
                      borderRadius: 14,
                      fontWeight: 700,
                      fontSize: 16,
                      cursor: "pointer",
                      fontFamily: "inherit",
                    }}
                  >
                    {unlocking
                      ? "Unlocking…"
                      : `Unlock Instructions — £${job.instructions_price_gbp ?? 5}`}
                  </button>
                )}
              </div>
              {!job.instructions_unlocked && (
                <p style={{ color: colors.textSecondary, fontSize: 12, marginTop: 8, marginBottom: 0 }}>
                  Demo only — no real payment yet (Stripe integration coming later).
                </p>
              )}

              <p style={{ color: colors.textSecondary, fontSize: 14, marginTop: 18, lineHeight: 1.6 }}>
                Open the .ldr in BrickLink Studio (free) for its own stability check and
                step-by-step instructions.
                {job.was_repaired && " Structural repair ran on this model to connect or remove unsupported pieces."}
                {job.color_source === "reference_image_projection" &&
                  " Colors were projected from the reference image, since the 3D stage returns geometry only."}
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function ProgressTrack({
  colors,
  status,
  studs,
}: {
  colors: ThemeColors;
  status: Job["status"];
  studs: number | null;
}) {
  const currentIndex = STATUS_ORDER.indexOf(status);
  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 4 }}>
        <div
          style={{
            width: 18,
            height: 18,
            border: `3px solid ${colors.accent}`,
            borderTopColor: "transparent",
            borderRadius: "50%",
            animation: "spin 0.9s linear infinite",
          }}
        />
        <span className="display" style={{ fontWeight: 700, fontSize: 20, color: colors.textPrimary }}>
          {STATUS_LABELS[status]}
        </span>
      </div>
      {studs != null && (
        <p style={{ color: colors.textSecondary, fontSize: 13, margin: "0 0 20px 30px" }}>
          Building at {studs} studs wide
        </p>
      )}
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {STATUS_ORDER.slice(0, -1).map((s, i) => {
          const done = i < currentIndex;
          const active = i === currentIndex;
          return (
            <div key={s} style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <div
                style={{
                  width: 10,
                  height: 10,
                  borderRadius: 3,
                  background: done || active ? colors.accent : colors.cardBorder,
                  opacity: done ? 0.6 : 1,
                }}
              />
              <span
                style={{
                  fontSize: 15,
                  color: active ? colors.textPrimary : colors.textSecondary,
                  fontWeight: active ? 700 : 500,
                }}
              >
                {STATUS_LABELS[s]}
              </span>
            </div>
          );
        })}
      </div>
      <p style={{ color: colors.textSecondary, fontSize: 14, marginTop: 22, marginBottom: 0 }}>
        This takes a few minutes — image generation, then 3D reconstruction, then the
        brick solver.
      </p>
    </div>
  );
}

function Card({
  colors,
  children,
  padded = true,
}: {
  colors: ThemeColors;
  children: React.ReactNode;
  padded?: boolean;
}) {
  return (
    <div
      style={{
        background: colors.cardBg,
        border: `1px solid ${colors.cardBorder}`,
        borderRadius: 20,
        padding: padded ? 32 : 8,
        marginBottom: 16,
      }}
    >
      {children}
    </div>
  );
}

function Stat({ colors, label, value }: { colors: ThemeColors; label: string; value: string }) {
  return (
    <div
      style={{
        background: colors.cardBg,
        border: `1px solid ${colors.cardBorder}`,
        borderRadius: 16,
        padding: "20px 22px",
      }}
    >
      <div style={{ color: colors.textSecondary, fontSize: 13, marginBottom: 6 }}>{label}</div>
      <div className="display" style={{ fontWeight: 800, fontSize: 26, color: colors.textPrimary }}>
        {value}
      </div>
    </div>
  );
}
