"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import Nav from "@/components/Nav";
import Scenery from "@/components/Scenery";
import { useTheme } from "@/components/ThemeProvider";
import { ThemeColors, darkColors, lightColors } from "@/app/theme";
import { GalleryCard as GalleryCardType, fetchPublicGallery, thumbnailUrl } from "@/lib/api";

// Public -- no auth guard. Deliberately kept simple with local input
// state rather than a ?q= URL param, since a shareable search URL isn't
// worth the extra useSearchParams()-needs-Suspense boilerplate (see
// AuthForm.tsx's own comment on that) for a first pass at this feature.
export default function DiscoverPage() {
  const { dark, toggleDark } = useTheme();
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<GalleryCardType[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const colors = dark ? darkColors : lightColors;

  useEffect(() => {
    let cancelled = false;
    // Debounced so every keystroke doesn't fire its own request.
    const timer = setTimeout(() => {
      fetchPublicGallery(query)
        .then((data) => {
          if (!cancelled) setItems(data);
        })
        .catch((err) => {
          if (!cancelled) setError((err as Error).message);
        });
    }, 300);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [query]);

  return (
    <div style={{ position: "relative", minHeight: "100vh", background: colors.skyBottom, overflowX: "hidden" }}>
      <Scenery colors={colors} dark={dark} prominence={0.35} />
      <div style={{ position: "relative", zIndex: 2 }}>
        <Nav colors={colors} dark={dark} onToggleDark={toggleDark} />

        <div style={{ maxWidth: 1100, margin: "0 auto", padding: "48px 24px 100px" }}>
          <h1 className="display" style={{ fontWeight: 800, fontSize: 34, color: colors.textPrimary, margin: "0 0 6px" }}>
            Discover
          </h1>
          <p style={{ color: colors.textSecondary, fontSize: 15, marginBottom: 24 }}>
            Real builds other people have made and shared.
          </p>

          <input
            type="text"
            placeholder="Search builds…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            style={{
              width: "100%",
              maxWidth: 420,
              padding: "12px 16px",
              borderRadius: 12,
              border: `1px solid ${colors.inputBorder}`,
              background: colors.cardBg,
              color: colors.textPrimary,
              fontSize: 15,
              outline: "none",
              fontFamily: "inherit",
              marginBottom: 32,
              display: "block",
            }}
          />

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

          {!error && items === null && <p style={{ color: colors.textSecondary }}>Loading…</p>}

          {items !== null && items.length === 0 && (
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
                {query ? "No builds match that search." : "Nothing published yet — be the first."}
              </p>
            </div>
          )}

          {items !== null && items.length > 0 && (
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))",
                gap: 20,
              }}
            >
              {items.map((item) => (
                <DiscoverCard key={item.job_id} colors={colors} item={item} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function DiscoverCard({ colors, item }: { colors: ThemeColors; item: GalleryCardType }) {
  const thumbSrc = item.thumbnail_url ? thumbnailUrl(item.job_id) : undefined;
  return (
    <Link
      href={`/discover/${item.job_id}`}
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
          {item.prompt}
        </div>
        <div style={{ color: colors.textSecondary, fontSize: 13, marginTop: 6 }}>
          {item.part_count?.toLocaleString() ?? "—"} parts · £{item.instructions_price_gbp}
        </div>
      </div>
    </Link>
  );
}
