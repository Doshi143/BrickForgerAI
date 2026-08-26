"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, use, useEffect, useState } from "react";

import Nav from "@/components/Nav";
import Scenery from "@/components/Scenery";
import { useActiveJob } from "@/components/ActiveJobProvider";
import { useAuth } from "@/components/AuthProvider";
import { useTheme } from "@/components/ThemeProvider";
import { ThemeColors, darkColors, lightColors } from "@/app/theme";
import {
  ApiError,
  Job,
  STATUS_LABELS,
  STATUS_ORDER,
  downloadInstructionsPdf,
  downloadLdr,
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
// After returning from a real Stripe Checkout for the instructions
// unlock, the webhook that actually flips instructions_unlocked hasn't
// necessarily landed yet by the time the browser redirects back here --
// keep polling a bounded number of extra times rather than leaving the
// page stuck showing "locked" right after a real payment succeeded.
const POST_CHECKOUT_MAX_EXTRA_POLLS = 6;

export default function GeneratePage({ params }: { params: Promise<{ jobId: string }> }) {
  return (
    <Suspense fallback={null}>
      <GenerateContent params={params} />
    </Suspense>
  );
}

function GenerateContent({ params }: { params: Promise<{ jobId: string }> }) {
  const { jobId } = use(params);
  const { dark, toggleDark } = useTheme();
  const { token } = useAuth();
  const { activeJobId, dismiss: dismissActiveJob } = useActiveJob();
  const searchParams = useSearchParams();
  const checkoutStatus = searchParams.get("checkout");
  const [job, setJob] = useState<Job | null>(null);
  const [pollError, setPollError] = useState<string | null>(null);
  const [unlocking, setUnlocking] = useState(false);
  const [unlockError, setUnlockError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  // One click, one unlock, both files -- the .ldr and (when it rendered
  // successfully for this job) its PDF build guide download together,
  // since they're never charged or gated separately (see main.py's
  // download_instructions_pdf: identical gating to download_ldr). Two
  // separate buttons here would just be presenting one already-bundled
  // purchase as if it were two, which is what prompted this change.
  async function handleDownload() {
    if (!token || downloading || !job) return;
    setDownloading(true);
    setDownloadError(null);
    try {
      await downloadLdr(jobId, token);
      if (job.instructions_pdf_url) {
        await downloadInstructionsPdf(jobId, token);
      }
    } catch (err) {
      setDownloadError(err instanceof ApiError ? err.message : "Couldn't download. Try again.");
    } finally {
      setDownloading(false);
    }
  }

  async function handleUnlock() {
    if (!token || unlocking) return;
    setUnlocking(true);
    setUnlockError(null);
    try {
      const { checkout_url } = await unlockInstructions(jobId, token);
      window.location.href = checkout_url;
    } catch (err) {
      setUnlockError(err instanceof ApiError ? err.message : "Couldn't start checkout. Try again.");
      setUnlocking(false);
    }
  }

  const colors = dark ? darkColors : lightColors;

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    let extraPolls = 0;

    async function poll() {
      try {
        const next = await fetchJob(jobId);
        if (cancelled) return;
        setJob(next);
        setPollError(null);
        const stillWorking = next.status !== "done" && next.status !== "failed";
        // Once the job itself is done, keep polling a few more times only
        // if we're specifically waiting on a checkout-confirmed unlock
        // that hasn't shown up yet -- not indefinitely, and not for any
        // other reason.
        const waitingOnUnlockWebhook =
          checkoutStatus === "success" && !next.instructions_unlocked && extraPolls < POST_CHECKOUT_MAX_EXTRA_POLLS;
        if (stillWorking || waitingOnUnlockWebhook) {
          if (!stillWorking) extraPolls += 1;
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
  }, [jobId, checkoutStatus]);

  // Once you've actually landed here and seen a finished (or failed)
  // result for the job the floating bar was tracking, there's nothing
  // left for that bar to tell you -- clear it so it doesn't keep nagging
  // about a result you've already viewed. Only fires for *this* job, so
  // viewing an old/unrelated job's page never clears a different,
  // still-in-progress tracked job.
  useEffect(() => {
    if (jobId === activeJobId && job && (job.status === "done" || job.status === "failed")) {
      dismissActiveJob();
    }
  }, [jobId, activeJobId, job, dismissActiveJob]);

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
                {job.symmetrized && <Stat colors={colors} label="Symmetry" value="Matched" />}
              </div>

              <div style={{ display: "flex", gap: 14, marginTop: 28, flexWrap: "wrap" }}>
                {job.instructions_unlocked ? (
                  <button
                    onClick={handleDownload}
                    disabled={downloading}
                    style={{
                      background: colors.accent,
                      color: "#fff",
                      padding: "16px 28px",
                      borderRadius: 14,
                      fontWeight: 700,
                      fontSize: 16,
                      border: "none",
                      cursor: "pointer",
                      fontFamily: "inherit",
                      opacity: downloading ? 0.6 : 1,
                    }}
                  >
                    {downloading
                      ? "Downloading…"
                      : job.instructions_pdf_url
                        ? "Download .ldr + instructions (PDF) ↓"
                        : "Download .ldr ↓"}
                  </button>
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
                      ? "Redirecting…"
                      : `Unlock Instructions — £${job.instructions_price_gbp ?? 5}`}
                  </button>
                )}
              </div>
              {unlockError && (
                <p style={{ color: "#ff8f6b", fontSize: 13, marginTop: 8, marginBottom: 0 }}>{unlockError}</p>
              )}
              {downloadError && (
                <p style={{ color: "#ff8f6b", fontSize: 13, marginTop: 8, marginBottom: 0 }}>{downloadError}</p>
              )}
              {!job.instructions_unlocked && checkoutStatus === "success" && (
                <p style={{ color: colors.textSecondary, fontSize: 12, marginTop: 8, marginBottom: 0 }}>
                  Payment received — confirming now, this usually takes just a few seconds.
                </p>
              )}

              <p style={{ color: colors.textSecondary, fontSize: 14, marginTop: 18, lineHeight: 1.6 }}>
                {job.instructions_pdf_url
                  ? "Your build-instruction PDF walks through the model step by step, bottom-up. You can also open the .ldr in BrickLink Studio (free) for its own stability check."
                  : "Open the .ldr in BrickLink Studio (free) for its own stability check and step-by-step instructions."}
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
        This takes a few minutes — imagining the idea, then sculpting it in 3D, then
        the brick placer.
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
