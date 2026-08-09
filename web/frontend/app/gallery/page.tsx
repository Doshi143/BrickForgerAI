"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import Nav from "@/components/Nav";
import Scenery from "@/components/Scenery";
import { useAuth } from "@/components/AuthProvider";
import { useTheme } from "@/components/ThemeProvider";
import { ThemeColors, darkColors, lightColors } from "@/app/theme";
import {
  ApiError,
  Job,
  fetchGallery,
  previewUrl,
  publishToGallery,
  saveRender,
  thumbnailUrl,
  unpublishFromGallery,
} from "@/lib/api";

// three.js touches `window` at import time, so it can never run during SSR.
const Viewer3D = dynamic(() => import("@/components/Viewer3D"), { ssr: false });

export default function GalleryPage() {
  const router = useRouter();
  const { dark, toggleDark } = useTheme();
  const { token, loading: authLoading } = useAuth();
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Bumped per job once a backfilled render finishes uploading, so its
  // GalleryCard's background-image URL changes and the browser re-fetches
  // the now-real thumbnail instead of quietly keeping the AI photo it
  // loaded on first paint.
  const [thumbVersions, setThumbVersions] = useState<Record<string, number>>({});

  const colors = dark ? darkColors : lightColors;

  // This page is now a personal build history, not a public showcase --
  // the backend scopes /generate to the caller's own jobs and requires
  // auth, so an unauthenticated visit has nothing to show. Gate on
  // AuthProvider's own `loading` flag rather than `token` alone -- it
  // starts false while a stored token is still being revalidated against
  // the backend, so checking `!token` by itself would redirect a real
  // signed-in user for a split second on every load.
  useEffect(() => {
    if (!authLoading && !token) {
      router.push(`/signin?next=${encodeURIComponent("/gallery")}`);
    }
  }, [authLoading, token, router]);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    fetchGallery(token)
      .then((data) => {
        if (!cancelled) setJobs(data);
      })
      .catch((err) => {
        if (!cancelled) setError((err as Error).message);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  // There's no server-side LDraw renderer in this trial app (see
  // Viewer3D.tsx) -- a job's real 3D-render thumbnail only ever gets
  // captured client-side, the first time *someone's* browser opens that
  // job's model. A job whose results page nobody has visited yet has no
  // render.png, so GET .../thumbnail correctly (by the backend's own
  // documented fallback) serves the AI reference photo instead -- which
  // reads as "the gallery still shows the AI image" even though the
  // thumbnail endpoint itself isn't broken. Backfill it here: mount a
  // hidden Viewer3D for any completed job missing a render so visiting
  // the gallery alone is enough to eventually populate every thumbnail,
  // without requiring a visit to each job's own results page first.
  const jobsNeedingBackfill = (jobs ?? []).filter((j) => j.status === "done" && !j.has_render);

  const monthLabel = new Date().toLocaleString("en-GB", { month: "long", year: "numeric" });

  return (
    <div style={{ position: "relative", minHeight: "100vh", background: colors.skyBottom, overflowX: "hidden" }}>
      <Scenery colors={colors} dark={dark} prominence={0.35} />
      <div style={{ position: "relative", zIndex: 2 }}>
        <Nav colors={colors} dark={dark} onToggleDark={toggleDark} />

        <div style={{ maxWidth: 1100, margin: "0 auto", padding: "48px 24px 100px" }}>
          <h1 className="display" style={{ fontWeight: 800, fontSize: 34, color: colors.textPrimary, margin: "0 0 6px" }}>
            My Builds
          </h1>
          <p style={{ color: colors.textSecondary, fontSize: 15, marginBottom: 32 }}>
            Your builds in {monthLabel}
          </p>

          {error && (
            <div
              style={{
                background: colors.cardBg,
                border: `1px solid ${colors.cardBorder}`,
                borderRadius: 16,
                padding: 24,
                color: "#ff8f6b",
              }}
            >
              Can&apos;t reach the backend ({error}).
            </div>
          )}

          {!error && jobs === null && (
            <p style={{ color: colors.textSecondary }}>Loading…</p>
          )}

          {jobs !== null && jobs.length === 0 && (
            <div
              style={{
                background: colors.cardBg,
                border: `1px solid ${colors.cardBorder}`,
                borderRadius: 16,
                padding: 40,
                textAlign: "center",
              }}
            >
              <p style={{ color: colors.textSecondary, fontSize: 16, margin: 0 }}>
                Nothing generated yet this month.
              </p>
              <Link
                href="/"
                style={{
                  display: "inline-block",
                  marginTop: 18,
                  color: colors.accent,
                  fontWeight: 700,
                  textDecoration: "none",
                }}
              >
                Build the first one →
              </Link>
            </div>
          )}

          {jobs !== null && jobs.length > 0 && (
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))",
                gap: 20,
              }}
            >
              {jobs.map((job) => (
                <GalleryCard
                  key={job.job_id}
                  colors={colors}
                  job={job}
                  cacheBust={thumbVersions[job.job_id]}
                  token={token ?? ""}
                  onTogglePublish={(jobId, nextPublished) =>
                    setJobs((prev) =>
                      prev?.map((j) => (j.job_id === jobId ? { ...j, is_published: nextPublished } : j)) ?? prev
                    )
                  }
                />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Off-screen (not display:none -- a non-rendered canvas never
          produces a frame to capture), one per job missing a real render.
          Unmounts itself via the key change below once its onRendered
          fires once, so it doesn't keep re-rendering after backfill. */}
      {jobsNeedingBackfill.map((job) => (
        <div key={job.job_id} style={{ position: "fixed", top: -9999, left: -9999, width: 256, height: 256 }}>
          <Viewer3D
            src={previewUrl(job.job_id)}
            height={256}
            onRendered={(dataUrl) => {
              saveRender(job.job_id, dataUrl)
                .then(() => {
                  setThumbVersions((prev) => ({ ...prev, [job.job_id]: (prev[job.job_id] ?? 0) + 1 }));
                  setJobs((prev) => prev?.map((j) => (j.job_id === job.job_id ? { ...j, has_render: true } : j)) ?? prev);
                })
                .catch(() => {
                  // Cosmetic only -- next gallery visit just retries the backfill.
                });
            }}
          />
        </div>
      ))}
    </div>
  );
}

function GalleryCard({
  colors,
  job,
  cacheBust,
  token,
  onTogglePublish,
}: {
  colors: ThemeColors;
  job: Job;
  cacheBust?: number;
  token: string;
  onTogglePublish: (jobId: string, nextPublished: boolean) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const date = job.created_at
    ? new Date(job.created_at).toLocaleDateString("en-GB", { day: "numeric", month: "short" })
    : null;
  const thumbSrc = job.thumbnail_url
    ? `${thumbnailUrl(job.job_id)}${cacheBust ? `?v=${cacheBust}` : ""}`
    : undefined;

  // A <button> can't be nested inside the <Link> below (invalid HTML,
  // and a click would fire both the button and the navigation) -- kept
  // as a sibling row instead, its own click never triggers the link.
  async function handleToggle() {
    if (busy || !token) return;
    setBusy(true);
    setError(null);
    try {
      if (job.is_published) {
        await unpublishFromGallery(job.job_id, token);
        onTogglePublish(job.job_id, false);
      } else {
        await publishToGallery(job.job_id, token);
        onTogglePublish(job.job_id, true);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      style={{
        background: colors.cardBg,
        border: `1px solid ${colors.cardBorder}`,
        borderRadius: 16,
        overflow: "hidden",
      }}
    >
      <Link href={`/generate/${job.job_id}`} style={{ display: "block", textDecoration: "none" }}>
        <div
          style={{
            aspectRatio: "1 / 1",
            background: colors.badgeBg,
            backgroundImage: thumbSrc ? `url(${thumbSrc})` : undefined,
            backgroundSize: "cover",
            backgroundPosition: "center",
          }}
        />
        <div style={{ padding: "14px 16px 10px" }}>
          <div
            style={{
              color: colors.textPrimary,
              fontWeight: 700,
              fontSize: 15,
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
          >
            {job.prompt}
          </div>
          <div style={{ color: colors.textSecondary, fontSize: 13, marginTop: 6 }}>
            {job.part_count?.toLocaleString() ?? "—"} parts{date ? ` · ${date}` : ""}
          </div>
        </div>
      </Link>
      <div style={{ padding: "0 16px 14px", display: "flex", flexDirection: "column", gap: 6 }}>
        <button
          onClick={handleToggle}
          disabled={busy}
          style={{
            background: job.is_published ? "none" : colors.accent,
            border: job.is_published ? `1px solid ${colors.cardBorder}` : "none",
            color: job.is_published ? colors.textSecondary : "#fff",
            padding: "8px 12px",
            borderRadius: 10,
            fontWeight: 700,
            fontSize: 12,
            cursor: "pointer",
            fontFamily: "inherit",
            opacity: busy ? 0.6 : 1,
          }}
        >
          {busy ? "…" : job.is_published ? "Published — remove from Gallery" : "Publish to Gallery"}
        </button>
        {error && <span style={{ color: "#ff8f6b", fontSize: 12 }}>{error}</span>}
      </div>
    </div>
  );
}
