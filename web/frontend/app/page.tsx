"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import Logo from "@/components/Logo";
import Nav from "@/components/Nav";
import Scenery from "@/components/Scenery";
import WaitlistForm from "@/components/WaitlistForm";
import { useActiveJob } from "@/components/ActiveJobProvider";
import { useAuth } from "@/components/AuthProvider";
import { useTheme } from "@/components/ThemeProvider";
import { ThemeColors, darkColors, glassBlurStyle, lightColors } from "./theme";
import { ApiError, BuildSize, MAINTENANCE_MODE, SIZE_OPTIONS, startGeneration } from "@/lib/api";

const STEPS = [
  {
    icon: "⚡",
    num: "01",
    title: "Describe Your Vision",
    desc: "Type what you want to build. A spaceship, a house, a dragon - anything you can imagine.",
  },
  {
    icon: "👁",
    num: "02",
    title: "Preview Your Model",
    desc: "See it in 3D, with part count and dominant colors, before you commit to building it.",
  },
  {
    icon: "↓",
    num: "03",
    title: "Build It For Real",
    desc: "Download the .ldr file and a full step-by-step PDF build guide, included with your purchase - then order the bricks and start building.",
  },
];

// The old capability paragraph's own facts, distilled into scannable
// icon+label chips instead of one dense sentence -- same underlying
// claims (real part count, structural checking, best-fit use case,
// prompt tips), just packaged to be read at a glance rather than parsed
// as prose.
const CAPABILITY_STATS = [
  { icon: "🧱", label: "55-part real brick library" },
  { icon: "🔗", label: "100% connectivity checked" },
  { icon: "🌿", label: "Best on organic shapes" },
  { icon: "✍️", label: "More detail = better results" },
];

// A darker shade of the accent color for the "bricks" headline's own hard
// drop-shadow (see the Bungee treatment below) -- computed from colors.accent
// itself rather than a separate hardcoded hex per theme, so it stays in sync
// if the accent color ever changes.
function darken(hex: string, amount: number): string {
  const n = parseInt(hex.slice(1), 16);
  const r = Math.max(0, Math.round(((n >> 16) & 255) * (1 - amount)));
  const g = Math.max(0, Math.round(((n >> 8) & 255) * (1 - amount)));
  const b = Math.max(0, Math.round((n & 255) * (1 - amount)));
  return `rgb(${r}, ${g}, ${b})`;
}

export default function Home() {
  const router = useRouter();
  const { dark, toggleDark } = useTheme();
  const { user, token } = useAuth();
  const { startTracking } = useActiveJob();
  const [prompt, setPrompt] = useState("");
  const [size, setSize] = useState<BuildSize>("medium");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const colors = dark ? darkColors : lightColors;

  // Size defaulted to "medium" on every fresh page load with no way to
  // stick -- confirmed as the real cause behind two separate reports of
  // "I picked Small but got a bigger build": the selection was real, it
  // just didn't survive a reload or an auth redirect back to "/". Persist
  // the last choice instead of re-defaulting every time.
  useEffect(() => {
    const saved = window.localStorage.getItem("brickforge_build_size");
    if (saved === "small" || saved === "medium" || saved === "large") {
      setSize(saved);
    }
  }, []);

  function handleSetSize(id: BuildSize) {
    setSize(id);
    window.localStorage.setItem("brickforge_build_size", id);
  }

  async function handleGenerate() {
    const trimmed = prompt.trim();
    if (!trimmed || submitting) return;

    if (!token) {
      router.push(`/signin?next=${encodeURIComponent("/")}`);
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      const studs = SIZE_OPTIONS.find((s) => s.id === size)!.studs;
      const { job_id } = await startGeneration(trimmed, studs, token);
      startTracking(job_id);
      router.push(`/generate/${job_id}`);
    } catch (err) {
      if (err instanceof ApiError && err.status === 402) {
        setError("You're out of credits this month. Upgrade on the pricing page for more.");
      } else if (err instanceof ApiError && err.status === 401) {
        router.push(`/signin?next=${encodeURIComponent("/")}`);
      } else if (err instanceof ApiError) {
        // Any other ApiError means the backend responded -- just a
        // rejection (content filter, validation, etc.), not an outage --
        // so show its message as-is instead of the "is the backend
        // running" suffix below, which only makes sense when the backend
        // never responded at all.
        setError(err.message);
      } else {
        setError(
          `${(err as Error).message}. Is the backend running on ${
            process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"
          }?`
        );
      }
      setSubmitting(false);
    }
  }

  return (
    <div
      style={{
        position: "relative",
        minHeight: "100vh",
        background: colors.skyBottom,
        overflowX: "hidden",
        transition: "background 0.4s",
      }}
    >
      <Scenery colors={colors} dark={dark} />

      <div style={{ position: "relative", zIndex: 2 }}>
        <Nav colors={colors} dark={dark} onToggleDark={toggleDark} />

        <div style={{ textAlign: "center", padding: "110px 24px 180px", maxWidth: 920, margin: "0 auto" }}>
          <h1
            className="hero-title"
            style={{
              fontWeight: 800,
              fontSize: 64,
              lineHeight: 1.1,
              color: colors.textPrimary,
              margin: 0,
            }}
          >
            <span style={{ fontFamily: "'Rubik', sans-serif", fontWeight: 800 }}>Build anything with</span>
            <br />
            <span
              style={{
                fontFamily: "'Bungee', sans-serif",
                color: colors.accent,
                textShadow: `4px 5px 0 ${darken(colors.accent, 0.35)}`,
              }}
            >
              bricks
            </span>
          </h1>
          <p
            style={{
              fontSize: 20,
              color: colors.textSecondary,
              margin: "32px auto 0",
              maxWidth: 680,
              lineHeight: 1.6,
              textShadow: `0 1px 12px ${colors.heroTextShadow}`,
            }}
          >
            Type a prompt. Get a custom model with a downloadable .ldr file, full parts
            list, and step-by-step PDF build instructions. From imagination to physical kit
            in minutes.
          </p>

          {MAINTENANCE_MODE ? (
            <WaitlistForm colors={colors} />
          ) : (
            <>
              <div
                className="prompt-row"
                style={{
                  display: "flex",
                  gap: 14,
                  justifyContent: "center",
                  marginTop: 40,
                  maxWidth: 640,
                  marginLeft: "auto",
                  marginRight: "auto",
                }}
              >
                <input
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleGenerate()}
                  disabled={submitting}
                  placeholder="A stylized cartoon pineapple..."
                  style={{
                    flex: 1,
                    padding: "18px 22px",
                    borderRadius: 14,
                    border: `1px solid ${colors.inputBorder}`,
                    background: colors.cardBg,
                    color: colors.textPrimary,
                    fontSize: 16,
                    outline: "none",
                    fontFamily: "inherit",
                    ...glassBlurStyle,
                  }}
                />
                <button
                  onClick={handleGenerate}
                  disabled={submitting || !prompt.trim()}
                  style={{
                    background: colors.accent,
                    color: "#fff",
                    border: "none",
                    padding: "18px 30px",
                    borderRadius: 14,
                    fontWeight: 700,
                    fontSize: 16,
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    cursor: "pointer",
                    fontFamily: "inherit",
                    whiteSpace: "nowrap",
                  }}
                >
                  {submitting ? "Starting…" : "Generate →"}
                </button>
              </div>

              {error && (
                <p style={{ color: "#ff8f6b", marginTop: 18, fontSize: 15, maxWidth: 640, marginInline: "auto" }}>
                  {error}
                </p>
              )}

              <div
                style={{
                  display: "flex",
                  gap: 10,
                  justifyContent: "center",
                  marginTop: 22,
                  maxWidth: 640,
                  marginLeft: "auto",
                  marginRight: "auto",
                }}
              >
                {SIZE_OPTIONS.map((opt) => {
                  const active = size === opt.id;
                  return (
                    <button
                      key={opt.id}
                      type="button"
                      onClick={() => handleSetSize(opt.id)}
                      title={opt.hint}
                      style={{
                        flex: 1,
                        padding: "10px 14px",
                        borderRadius: 12,
                        border: `1px solid ${active ? colors.accent : colors.cardBorder}`,
                        // Dark mode's own badgeBg is already a translucent
                        // rgba tint, which reads as "transparent" -- light
                        // mode's is a solid opaque swatch instead. Day and
                        // evening both use the light palette (dark is only
                        // true for night), so this one translucent override
                        // covers both at once, matching the look already
                        // working for night without touching the shared
                        // badgeBg token other badges/pills also use.
                        background: active ? (dark ? colors.badgeBg : "rgba(232,129,58,0.15)") : colors.cardBg,
                        color: active ? colors.accent : colors.textSecondary,
                        fontWeight: active ? 700 : 600,
                        fontSize: 14,
                        fontFamily: "inherit",
                        cursor: "pointer",
                        ...glassBlurStyle,
                      }}
                    >
                      {opt.label}
                      <span style={{ display: "block", fontSize: 11, fontWeight: 500, opacity: 0.8, marginTop: 2 }}>
                        {opt.studs} studs
                      </span>
                    </button>
                  );
                })}
              </div>
              <p style={{ color: colors.textSecondary, marginTop: 10, fontSize: 13 }}>
                Build size - {SIZE_OPTIONS.find((s) => s.id === size)!.hint}
              </p>

              <p
                style={{
                  display: "inline-block",
                  color: colors.textSecondary,
                  marginTop: 20,
                  fontSize: 15,
                  padding: "8px 20px",
                  borderRadius: 999,
                  background: colors.cardBg,
                  border: `1px solid ${colors.cardBorder}`,
                  ...glassBlurStyle,
                }}
              >
                {user
                  ? `${user.credits_remaining} credit${user.credits_remaining === 1 ? "" : "s"} left this month`
                  : "£1.50/month: 3 generations, with the .ldr file and instructions included"}
              </p>
            </>
          )}
          <div
            style={{
              display: "flex",
              flexWrap: "nowrap",
              justifyContent: "center",
              gap: 10,
              marginTop: 20,
              // Wide enough to hold all 4 chips in one row on a normal
              // desktop width; overflowX is a fallback for anything
              // narrower rather than letting them wrap or clip.
              maxWidth: "100%",
              overflowX: "auto",
              paddingBottom: 4,
            }}
          >
            {CAPABILITY_STATS.map((stat) => (
              <div
                key={stat.label}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  padding: "8px 14px",
                  borderRadius: 999,
                  background: colors.cardBg,
                  border: `1px solid ${colors.cardBorder}`,
                  color: colors.textSecondary,
                  fontSize: 13,
                  fontWeight: 600,
                  whiteSpace: "nowrap",
                  flexShrink: 0,
                  ...glassBlurStyle,
                }}
              >
                <span style={{ fontSize: 15 }}>{stat.icon}</span>
                {stat.label}
              </div>
            ))}
          </div>
        </div>

        <div
          className="steps-grid"
          style={{
            maxWidth: 1100,
            margin: "0 auto",
            padding: "0 24px 100px",
            display: "grid",
            gridTemplateColumns: "repeat(3, 1fr)",
            gap: 28,
          }}
        >
          {STEPS.map((s) => (
            <div
              key={s.num}
              style={{
                background: colors.cardBg,
                borderRadius: 20,
                padding: "40px 32px",
                textAlign: "center",
                border: `1px solid ${colors.cardBorder}`,
                ...glassBlurStyle,
              }}
            >
              <div
                style={{
                  width: 64,
                  height: 64,
                  borderRadius: "50%",
                  background: colors.badgeBg,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  margin: "0 auto 20px",
                  fontSize: 26,
                  color: colors.accent,
                }}
              >
                {s.icon}
              </div>
              <div className="display" style={{ fontWeight: 800, fontSize: 40, color: colors.numColor, marginBottom: 8 }}>
                {s.num}
              </div>
              <div className="display" style={{ fontWeight: 700, fontSize: 22, color: colors.textPrimary, marginBottom: 12 }}>
                {s.title}
              </div>
              <div style={{ color: colors.textSecondary, fontSize: 16, lineHeight: 1.6 }}>{s.desc}</div>
            </div>
          ))}
        </div>

        <Footer colors={colors} />
      </div>
    </div>
  );
}

function Footer({ colors }: { colors: ThemeColors }) {
  return (
    <div style={{ padding: "60px 48px 40px", borderTop: `1px solid ${colors.cardBorder}`, background: colors.ctaBg }}>
      <div
        className="footer-grid"
        style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr", gap: 40, maxWidth: 1100, margin: "0 auto" }}
      >
        <div>
          <div
            className="display"
            style={{ display: "flex", alignItems: "center", gap: 5, fontWeight: 800, fontSize: 20, color: colors.textPrimary, marginBottom: 14 }}
          >
            <Logo size={27} />
            BrickForgerAI
          </div>
          <p style={{ color: colors.textSecondary, fontSize: 15, lineHeight: 1.6, maxWidth: 340 }}>
            Turn your imagination into buildable brick models. Prompt, preview, purchase -
            your custom kit is one idea away.
          </p>
          <p style={{ color: colors.textSecondary, fontSize: 13, lineHeight: 1.6, maxWidth: 340, marginTop: 14, opacity: 0.8 }}>
            Not affiliated with, endorsed, or sponsored by the LEGO Group, BrickLink, or Studio.
            LEGO®, BrickLink®, and Studio are trademarks of their respective owners. Part
            geometry from the LDraw parts library (CCAL 2.0).
          </p>
        </div>
        <div>
          <div style={{ fontWeight: 700, color: colors.textPrimary, marginBottom: 14 }}>Product</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 10, color: colors.textSecondary, fontSize: 15 }}>
            <FooterLink href="/how-it-works">How it Works</FooterLink>
            <FooterLink href="/pricing">Pricing</FooterLink>
            <FooterLink href="/gallery">My Builds</FooterLink>
          </div>
        </div>
        <div>
          <div style={{ fontWeight: 700, color: colors.textPrimary, marginBottom: 14 }}>Support</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 10, color: colors.textSecondary, fontSize: 15 }}>
            <FooterLink href="/help">Help Center</FooterLink>
            <FooterLink href="/terms">Terms of Service</FooterLink>
            <FooterLink href="/privacy">Privacy Policy</FooterLink>
          </div>
        </div>
      </div>
      <div
        style={{
          textAlign: "center",
          marginTop: 40,
          paddingTop: 24,
          borderTop: `1px solid ${colors.cardBorder}`,
        }}
      >
        <a
          href="https://www.producthunt.com/products/brickforgerai?embed=true&utm_source=badge-featured&utm_medium=badge&utm_campaign=badge-brickforgerai"
          target="_blank"
          rel="noopener noreferrer"
          style={{ display: "inline-block" }}
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            alt="BrickForgerAI - Turn any prompt into a brick set you can actually build | Product Hunt"
            width={250}
            height={54}
            src="https://api.producthunt.com/widgets/embed-image/v1/featured.svg?post_id=1239306&theme=light&t=1788700474913"
          />
        </a>
        <div style={{ color: colors.textSecondary, fontSize: 14, marginTop: 16 }}>
          © 2026 BrickForgerAI. Built with precision.
        </div>
      </div>
    </div>
  );
}

function FooterLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Link href={href} style={{ color: "inherit", textDecoration: "none" }}>
      {children}
    </Link>
  );
}
