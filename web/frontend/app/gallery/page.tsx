"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import Nav from "@/components/Nav";
import Scenery from "@/components/Scenery";
import { useTheme } from "@/components/ThemeProvider";
import { ThemeColors, darkColors, lightColors } from "@/app/theme";
import { Job, fetchGallery, thumbnailUrl } from "@/lib/api";

export default function GalleryPage() {
  const { dark, toggleDark } = useTheme();
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [error, setError] = useState<string | null>(null);

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
                <GalleryCard key={job.job_id} colors={colors} job={job} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function GalleryCard({ colors, job }: { colors: ThemeColors; job: Job }) {
  const date = job.created_at
    ? new Date(job.created_at).toLocaleDateString("en-GB", { day: "numeric", month: "short" })
    : null;

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
          backgroundImage: job.thumbnail_url ? `url(${thumbnailUrl(job.job_id)})` : undefined,
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
