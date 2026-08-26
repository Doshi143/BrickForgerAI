"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, use, useEffect, useState } from "react";

import Nav from "@/components/Nav";
import Scenery from "@/components/Scenery";
import { useAuth } from "@/components/AuthProvider";
import { useTheme } from "@/components/ThemeProvider";
import { ThemeColors, darkColors, lightColors } from "@/app/theme";
import {
  ApiError,
  GalleryDetail,
  downloadInstructionsPdf,
  downloadLdr,
  fetchGalleryAccess,
  fetchGalleryItem,
  previewUrl,
  startGalleryPurchaseCheckout,
} from "@/lib/api";

// three.js touches `window` at import time, so it can never run during SSR.
const Viewer3D = dynamic(() => import("@/components/Viewer3D"), {
  ssr: false,
  loading: () => <div style={{ height: 520 }} />,
});

// After a real Stripe Checkout redirect back here, the webhook that
// actually records the purchase hasn't necessarily landed yet -- retry a
// bounded number of times rather than leaving the page stuck showing
// "Buy" right after a payment that already succeeded. Same shape as
// app/generate/[jobId]/page.tsx's own POST_CHECKOUT_MAX_EXTRA_POLLS.
const POST_CHECKOUT_MAX_RETRIES = 5;
const POST_CHECKOUT_RETRY_MS = 2000;

export default function DiscoverItemPage({ params }: { params: Promise<{ jobId: string }> }) {
  return (
    <Suspense fallback={null}>
      <DiscoverItemContent params={params} />
    </Suspense>
  );
}

function DiscoverItemContent({ params }: { params: Promise<{ jobId: string }> }) {
  const { jobId } = use(params);
  const { dark, toggleDark } = useTheme();
  const { user, token } = useAuth();
  const searchParams = useSearchParams();
  const checkoutStatus = searchParams.get("checkout");

  const [item, setItem] = useState<GalleryDetail | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [access, setAccess] = useState<{ is_owner: boolean; has_access: boolean } | null>(null);
  const [buying, setBuying] = useState(false);
  const [buyError, setBuyError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const colors = dark ? darkColors : lightColors;

  useEffect(() => {
    let cancelled = false;
    fetchGalleryItem(jobId)
      .then((data) => {
        if (!cancelled) setItem(data);
      })
      .catch(() => {
        if (!cancelled) setNotFound(true);
      });
    return () => {
      cancelled = true;
    };
  }, [jobId]);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    let attempts = 0;

    function check() {
      fetchGalleryAccess(jobId, token as string)
        .then((data) => {
          if (cancelled) return;
          setAccess(data);
          const stillWaiting = checkoutStatus === "success" && !data.has_access && attempts < POST_CHECKOUT_MAX_RETRIES;
          if (stillWaiting) {
            attempts += 1;
            setTimeout(check, POST_CHECKOUT_RETRY_MS);
          }
        })
        .catch(() => {
          // Leave access as-is -- falls back to showing the Buy button,
          // which is the safe default if the check itself fails.
        });
    }
    check();
    return () => {
      cancelled = true;
    };
  }, [jobId, token, checkoutStatus]);

  async function handleBuy() {
    if (!token || buying) return;
    setBuying(true);
    setBuyError(null);
    try {
      const { checkout_url } = await startGalleryPurchaseCheckout(jobId, token);
      window.location.href = checkout_url;
    } catch (err) {
      setBuyError(err instanceof ApiError ? err.message : "Couldn't start checkout. Try again.");
      setBuying(false);
    }
  }

  // One click, one purchase, both files -- see the equivalent
  // app/generate/[jobId]/page.tsx::handleDownload for why this isn't two
  // separate buttons/downloads: the PDF is never charged or gated
  // separately from the .ldr (main.py's download_instructions_pdf uses
  // the identical has_gallery_access check).
  async function handleDownload() {
    if (!token || downloading || !item) return;
    setDownloading(true);
    setDownloadError(null);
    try {
      await downloadLdr(jobId, token);
      if (item.instructions_pdf_url) {
        await downloadInstructionsPdf(jobId, token);
      }
    } catch (err) {
      setDownloadError(err instanceof ApiError ? err.message : "Couldn't download. Try again.");
    } finally {
      setDownloading(false);
    }
  }

  if (notFound) {
    return (
      <div style={{ position: "relative", minHeight: "100vh", background: colors.skyBottom, overflowX: "hidden" }}>
        <Scenery colors={colors} dark={dark} prominence={0.35} />
        <div style={{ position: "relative", zIndex: 2 }}>
          <Nav colors={colors} dark={dark} onToggleDark={toggleDark} />
          <div style={{ maxWidth: 640, margin: "80px auto", textAlign: "center", padding: "0 24px" }}>
            <h1 className="display" style={{ color: colors.textPrimary, fontSize: 26, marginBottom: 12 }}>
              Not found
            </h1>
            <p style={{ color: colors.textSecondary, marginBottom: 20 }}>
              This build isn&apos;t in the gallery — it may have been unpublished.
            </p>
            <Link href="/discover" style={{ color: colors.accent, fontWeight: 700, textDecoration: "none" }}>
              ← Back to Discover
            </Link>
          </div>
        </div>
      </div>
    );
  }

  const hasAccess = access?.has_access ?? false;
  const isOwner = access?.is_owner ?? false;

  return (
    <div style={{ position: "relative", minHeight: "100vh", background: colors.skyBottom, overflowX: "hidden" }}>
      <Scenery colors={colors} dark={dark} prominence={0.35} />
      <div style={{ position: "relative", zIndex: 2 }}>
        <Nav colors={colors} dark={dark} onToggleDark={toggleDark} />

        <div style={{ maxWidth: 960, margin: "0 auto", padding: "48px 24px 100px" }}>
          <Link href="/discover" style={{ color: colors.textSecondary, fontSize: 15, textDecoration: "none" }}>
            ← Back to Discover
          </Link>

          <h1
            className="display"
            style={{ fontWeight: 800, fontSize: 34, color: colors.textPrimary, margin: "18px 0 28px" }}
          >
            {item?.prompt ?? "Loading…"}
          </h1>

          {item && (
            <>
              <div
                style={{
                  background: colors.cardBg,
                  border: `1px solid ${colors.cardBorder}`,
                  borderRadius: 20,
                  padding: 8,
                  marginBottom: 16,
                }}
              >
                <Viewer3D src={previewUrl(jobId)} />
              </div>

              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
                  gap: 16,
                  marginTop: 24,
                }}
              >
                <Stat colors={colors} label="Parts" value={item.part_count?.toLocaleString() ?? "—"} />
                <Stat colors={colors} label="Colors" value={item.color_count?.toString() ?? "—"} />
                <Stat colors={colors} label="Slopes" value={item.slope_count?.toString() ?? "—"} />
                <Stat colors={colors} label="Tiles" value={item.tile_count?.toString() ?? "—"} />
                {item.symmetrized && <Stat colors={colors} label="Symmetry" value="Matched" />}
              </div>

              <div style={{ marginTop: 28 }}>
                {isOwner ? (
                  <div>
                    <p style={{ color: colors.textSecondary, fontSize: 14, marginBottom: 12 }}>
                      This is your own published build.
                    </p>
                    <Link href={`/generate/${jobId}`} style={{ color: colors.accent, fontWeight: 700, textDecoration: "none" }}>
                      View in My Builds →
                    </Link>
                  </div>
                ) : hasAccess ? (
                  <button onClick={handleDownload} disabled={downloading} style={primaryButtonStyle(colors, downloading)}>
                    {downloading
                      ? "Downloading…"
                      : item.instructions_pdf_url
                        ? "Download .ldr + instructions (PDF) ↓"
                        : "Download .ldr ↓"}
                  </button>
                ) : !user ? (
                  <Link
                    href={`/signin?next=${encodeURIComponent(`/discover/${jobId}`)}`}
                    style={{ ...primaryButtonStyle(colors, false), display: "inline-block", textDecoration: "none" }}
                  >
                    Sign in to buy — £{item.instructions_price_gbp}
                  </Link>
                ) : (
                  <button onClick={handleBuy} disabled={buying} style={primaryButtonStyle(colors, buying)}>
                    {buying ? "Redirecting…" : `Buy this build — £${item.instructions_price_gbp}`}
                  </button>
                )}
                {buyError && <p style={{ color: "#ff8f6b", fontSize: 13, marginTop: 8, marginBottom: 0 }}>{buyError}</p>}
                {downloadError && (
                  <p style={{ color: "#ff8f6b", fontSize: 13, marginTop: 8, marginBottom: 0 }}>{downloadError}</p>
                )}
                {checkoutStatus === "success" && !hasAccess && (
                  <p style={{ color: colors.textSecondary, fontSize: 12, marginTop: 8, marginBottom: 0 }}>
                    Payment received — confirming now, this usually takes just a few seconds.
                  </p>
                )}
              </div>

              <p style={{ color: colors.textSecondary, fontSize: 14, marginTop: 18, lineHeight: 1.6 }}>
                Buying unlocks the downloadable .ldr file{item.instructions_pdf_url ? " and a step-by-step build-instruction PDF" : ""} for
                this specific build.
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function primaryButtonStyle(colors: ThemeColors, disabled: boolean): React.CSSProperties {
  return {
    background: colors.accent,
    color: "#fff",
    padding: "16px 28px",
    borderRadius: 14,
    fontWeight: 700,
    fontSize: 16,
    border: "none",
    cursor: "pointer",
    fontFamily: "inherit",
    opacity: disabled ? 0.6 : 1,
  };
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
