"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useState } from "react";

import Nav from "@/components/Nav";
import Scenery from "@/components/Scenery";
import { useTheme } from "@/components/ThemeProvider";
import { ThemeColors, darkColors, lightColors } from "@/app/theme";
import { Job, fetchGallery, previewUrl, saveRender, thumbnailUrl } from "@/lib/api";

// three.js touches `window` at import time, so it can never run during SSR.
const Viewer3D = dynamic(() => import("@/components/Viewer3D"), { ssr: false });

export default function GalleryPage() {
  const { dark, toggleDark } = useTheme();
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Bumped per job once a backfilled render finishes uploading, so its
  // GalleryCard's background-image URL changes and the browser re-fetches
  // the now-real thumbnail instead of quietly keeping the AI photo it
  // loaded on first paint.
  const [thumbVersions, setThumbVersions] = useState<Record<string, number>>({});

  const colors = dark ? darkColors : lightColors;

  useEffect(() => {
    let cancelled = false;
    fetchGallery()
      .then((data) => {
        if (!cancelled) setJobs(data);
      })
      .catch((err) => {
        if (!cancelled) setError((err as Error).message);
      });
    return () => {
      cancelled = true;
    };
  }, []);

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
            Gallery
          </h1>
          <p style={{ color: colors.textSecondary, fontSize: 15, marginBottom: 32 }}>
            Models generated in {monthLabel}
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
}: {
  colors: ThemeColors;
  job: Job;
  cacheBust?: number;
}) {
  const date = job.created_at
    ? new Date(job.created_at).toLocaleDateString("en-GB", { day: "numeric", month: "short" })
    : null;
  const thumbSrc = job.thumbnail_url
    ? `${thumbnailUrl(job.job_id)}${cacheBust ? `?v=${cacheBust}` : ""}`
    : undefined;

  return (
    <Link
      href={`/generate/${job.job_id}`}
      style={{
        display: "block",
        background: colors.cardBg,
        border: `1px solid ${colors.cardBorder}`,
        borderRadius: 16,
        overflow: "hidden",
        textDecoration: "none",
      }}
    >
      <div
        style={{
          aspectRatio: "1 / 1",
          background: colors.badgeBg,
          backgroundImage: thumbSrc ? `url(${thumbSrc})` : undefined,
          backgroundSize: "cover",
          backgroundPosition: "center",
        }}
      />
      <div style={{ padding: "14px 16px" }}>
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
  );
}
