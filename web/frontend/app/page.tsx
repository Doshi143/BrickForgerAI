"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import Logo from "@/components/Logo";
import Nav from "@/components/Nav";
import Scenery from "@/components/Scenery";
import WaitlistForm from "@/components/WaitlistForm";
import { useActiveJob } from "@/components/ActiveJobProvider";
import { SET_MODE_EVENT } from "@/components/DetailedBetaAnnouncement";
import { useAuth } from "@/components/AuthProvider";
import { useTheme } from "@/components/ThemeProvider";
import { ThemeColors, boostForEvening, darkColors, glassBlurStyle, lightColors } from "./theme";
import {
  ApiError,
  CREDIT_COST,
  Finish,
  GenerationMode,
  MAINTENANCE_MODE,
  SIZE_RANGE,
  Sideways,
  fetchFeatures,
  startGeneration,
} from "@/lib/api";

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
// as prose. Per mode, since the two pipelines are good at different things.
const CAPABILITY_STATS: Record<GenerationMode, { icon: string; label: string }[]> = {
  voxel: [
    { icon: "🧱", label: "55-part real brick library" },
    { icon: "🔗", label: "100% connectivity checked" },
    { icon: "🌿", label: "Best on organic shapes" },
    { icon: "✍️", label: "More detail = better results" },
  ],
  detailed: [
    { icon: "🧱", label: "70+ real brick parts" },
    { icon: "🔗", label: "Every connection checked" },
    { icon: "🏠", label: "Best on buildings and vehicles" },
    { icon: "✍️", label: "More detail = better results" },
  ],
};

const MODE_OPTIONS: { id: GenerationMode; label: string; hint: string }[] = [
  { id: "voxel", label: "Voxel", hint: "Sculpted from a generated 3D shape - best on organic forms. 1 credit." },
  {
    id: "detailed",
    label: "Detailed (beta)",
    hint: "Designed piece by piece with real building techniques - best on buildings, vehicles and animals. 2 credits.",
  },
];

const FINISH_OPTIONS: { id: Finish; label: string }[] = [
  { id: "tiled", label: "Smooth tiles" },
  { id: "studs", label: "Studs showing" },
];

const SIDEWAYS_OPTIONS: { id: Sideways; label: string }[] = [
  { id: "off", label: "Off" },
  { id: "auto", label: "Auto" },
  { id: "more", label: "More" },
];

// Saved choices -- each read/write guarded, since storage can be blocked
// (private windows, disabled site data) and the page must work without it.
function loadSetting(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function saveSetting(key: string, value: string) {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // not saved; the choice still applies for this visit
  }
}

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
  const { dark, toggleDark, sceneryTime } = useTheme();
  const { user, token } = useAuth();
  const { startTracking } = useActiveJob();
  const [prompt, setPrompt] = useState("");
  const [mode, setMode] = useState<GenerationMode>("voxel");
  const [sizes, setSizes] = useState<Record<GenerationMode, number>>({
    voxel: SIZE_RANGE.voxel.initial,
    detailed: SIZE_RANGE.detailed.initial,
  });
  const [finish, setFinish] = useState<Finish>("tiled");
  const [sideways, setSideways] = useState<Sideways>("auto");
  const [detailedAvailable, setDetailedAvailable] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const baseColors = dark ? darkColors : lightColors;
  // Evening's own backdrop makes the glass cards' shared opacity harder to
  // read against than day's -- see boostForEvening's own comment.
  const colors = sceneryTime === "evening" ? boostForEvening(baseColors) : baseColors;

  // Detailed mode only shows up where the backend says it's on for this
  // visitor (flag + beta allowlist); everyone else keeps seeing Voxel only.
  const activeMode: GenerationMode = detailedAvailable ? mode : "voxel";
  const studs = sizes[activeMode];
  const range = SIZE_RANGE[activeMode];

  useEffect(() => {
    let cancelled = false;
    fetchFeatures(token).then((f) => {
      if (!cancelled) setDetailedAvailable(f.detailed_mode);
    });
    return () => {
      cancelled = true;
    };
  }, [token]);

  // The size defaulted on every fresh page load with no way to stick --
  // confirmed as the real cause behind two separate reports of "I picked
  // Small but got a bigger build": the selection was real, it just didn't
  // survive a reload or an auth redirect back to "/". Persist every choice
  // instead of re-defaulting each time (a saved Small/Medium/Large from
  // before the slider maps to the studs those buttons used).
  useEffect(() => {
    const savedMode = loadSetting("brickforge_mode");
    if (savedMode === "voxel" || savedMode === "detailed") setMode(savedMode);
    const legacyStuds: Record<string, number> = { small: 15, medium: 22, large: 30 };
    const next: Record<GenerationMode, number> = {
      voxel: SIZE_RANGE.voxel.initial,
      detailed: SIZE_RANGE.detailed.initial,
    };
    for (const m of ["voxel", "detailed"] as GenerationMode[]) {
      let n = parseInt(loadSetting(`brickforge_size_${m}`) ?? "", 10);
      if (m === "voxel" && !Number.isFinite(n)) n = legacyStuds[loadSetting("brickforge_build_size") ?? ""] ?? NaN;
      if (Number.isFinite(n)) next[m] = Math.min(SIZE_RANGE[m].max, Math.max(SIZE_RANGE[m].min, n));
    }
    setSizes(next);
    const savedFinish = loadSetting("brickforge_finish");
    if (savedFinish === "tiled" || savedFinish === "studs") setFinish(savedFinish);
    const savedSideways = loadSetting("brickforge_sideways");
    if (savedSideways === "off" || savedSideways === "auto" || savedSideways === "more") setSideways(savedSideways);
  }, []);

  // "Try Detailed" in the beta announcement, while this page is already open
  useEffect(() => {
    const onSetMode = (e: Event) => {
      const m = (e as CustomEvent).detail;
      if (m === "voxel" || m === "detailed") setMode(m);
    };
    window.addEventListener(SET_MODE_EVENT, onSetMode);
    return () => window.removeEventListener(SET_MODE_EVENT, onSetMode);
  }, []);

  function handleSetMode(m: GenerationMode) {
    setMode(m);
    saveSetting("brickforge_mode", m);
  }

  function handleSetSize(n: number) {
    setSizes((prev) => ({ ...prev, [activeMode]: n }));
    saveSetting(`brickforge_size_${activeMode}`, String(n));
  }

  function handleSetFinish(f: Finish) {
    setFinish(f);
    saveSetting("brickforge_finish", f);
  }

  function handleSetSideways(s: Sideways) {
    setSideways(s);
    saveSetting("brickforge_sideways", s);
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
      const options = activeMode === "detailed" ? { mode: activeMode, finish, sideways } : {};
      const { job_id } = await startGeneration(trimmed, studs, token, options);
      startTracking(job_id);
      router.push(`/generate/${job_id}`);
    } catch (err) {
      if (err instanceof ApiError && err.status === 402) {
        setError(
          activeMode === "detailed" && (user?.credits_remaining ?? 0) > 0
            ? `Detailed builds use ${CREDIT_COST.detailed} credits and you have ${user?.credits_remaining}. Switch to Voxel, or top up on the pricing page.`
            : "You're out of credits this month. Upgrade on the pricing page for more."
        );
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

              <p style={{ color: colors.textSecondary, marginTop: 12, fontSize: 13, maxWidth: 640, marginInline: "auto" }}>
                {activeMode === "detailed"
                  ? "Describe the subject, not the bricks - choose the finish and how much sideways building to use below. Brick types and part counts can't be requested."
                  : "Describe the subject, not the bricks - the shape and colors are generated from your description, so brick types, part counts, and building techniques can't be requested."}
              </p>

              {error && (
                <p style={{ color: "#ff8f6b", marginTop: 18, fontSize: 15, maxWidth: 640, marginInline: "auto" }}>
                  {error}
                </p>
              )}

              <div style={{ maxWidth: 640, margin: "22px auto 0", display: "flex", flexDirection: "column", gap: 12 }}>
                {detailedAvailable && (
                  <div>
                    <Segmented colors={colors} dark={dark} options={MODE_OPTIONS} value={activeMode} onChange={handleSetMode} />
                    <p style={{ color: colors.textSecondary, margin: "8px 0 0", fontSize: 13 }}>
                      {MODE_OPTIONS.find((o) => o.id === activeMode)!.hint}
                    </p>
                  </div>
                )}

                <label
                  style={{
                    display: "block",
                    padding: "12px 18px",
                    borderRadius: 12,
                    border: `1px solid ${colors.cardBorder}`,
                    background: colors.cardBg,
                    textAlign: "left",
                    ...glassBlurStyle,
                  }}
                >
                  <span style={{ display: "flex", justifyContent: "space-between", fontSize: 14, color: colors.textSecondary }}>
                    <span style={{ fontWeight: 600 }}>Build size</span>
                    <span style={{ color: colors.accent, fontWeight: 700 }}>{studs} studs across</span>
                  </span>
                  <input
                    type="range"
                    min={range.min}
                    max={range.max}
                    step={1}
                    value={studs}
                    onChange={(e) => handleSetSize(parseInt(e.target.value, 10))}
                    aria-label="Build size in studs"
                    style={{ width: "100%", marginTop: 8, accentColor: colors.accent, cursor: "pointer" }}
                  />
                  <span style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: colors.textSecondary, opacity: 0.8 }}>
                    <span>{range.min} - quicker, fewer parts</span>
                    <span>{range.max} - more detail, more parts</span>
                  </span>
                </label>

                {activeMode === "detailed" && (
                  <div
                    className="detail-options"
                    style={{
                      display: "grid",
                      gridTemplateColumns: "1fr 1fr",
                      gap: 12,
                      textAlign: "left",
                      padding: "12px 18px",
                      borderRadius: 12,
                      border: `1px solid ${colors.cardBorder}`,
                      background: colors.cardBg,
                      ...glassBlurStyle,
                    }}
                  >
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 600, color: colors.textSecondary, marginBottom: 6 }}>Finish</div>
                      <Segmented colors={colors} dark={dark} options={FINISH_OPTIONS} value={finish} onChange={handleSetFinish} />
                    </div>
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 600, color: colors.textSecondary, marginBottom: 6 }}>
                        Sideways building
                      </div>
                      <Segmented colors={colors} dark={dark} options={SIDEWAYS_OPTIONS} value={sideways} onChange={handleSetSideways} />
                    </div>
                    <p style={{ gridColumn: "1 / -1", color: colors.textSecondary, margin: 0, fontSize: 12, lineHeight: 1.5 }}>
                      Sideways building (studs not on top) gives smoother curves and faces, but makes the model
                      harder to assemble. Off keeps every brick studs-up.
                    </p>
                  </div>
                )}
              </div>

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
                  ? `${user.credits_remaining} credit${user.credits_remaining === 1 ? "" : "s"} left this month` +
                    (activeMode === "detailed" ? ` - this build uses ${CREDIT_COST.detailed}` : "")
                  : detailedAvailable
                    ? "£1.50/month: 3 credits (Detailed builds use 2), with the .ldr file and instructions included"
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
            {CAPABILITY_STATS[activeMode].map((stat) => (
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

/** A row of glass pill buttons, one active -- the same look the old
 * Small/Medium/Large size buttons had, reused for mode, finish and sideways. */
function Segmented<T extends string>({
  colors,
  dark,
  options,
  value,
  onChange,
}: {
  colors: ThemeColors;
  dark: boolean;
  options: { id: T; label: string }[];
  value: T;
  onChange: (id: T) => void;
}) {
  return (
    <div role="radiogroup" style={{ display: "flex", gap: 8 }}>
      {options.map((opt) => {
        const active = value === opt.id;
        return (
          <button
            key={opt.id}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(opt.id)}
            style={{
              flex: 1,
              padding: "10px 12px",
              borderRadius: 12,
              border: `1px solid ${active ? colors.accent : colors.cardBorder}`,
              // Dark mode's own badgeBg is already a translucent rgba tint,
              // which reads as "transparent" -- light mode's is a solid opaque
              // swatch instead. Day and evening both use the light palette
              // (dark is only true for night), so this one translucent
              // override covers both at once, matching the look already
              // working for night without touching the shared badgeBg token
              // other badges/pills also use.
              background: active ? (dark ? colors.badgeBg : "rgba(232,129,58,0.15)") : colors.cardBg,
              color: active ? colors.accent : colors.textSecondary,
              fontWeight: active ? 700 : 600,
              fontSize: 14,
              fontFamily: "inherit",
              cursor: "pointer",
              whiteSpace: "nowrap",
              ...glassBlurStyle,
            }}
          >
            {opt.label}
          </button>
        );
      })}
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
            style={{
              display: "flex",
              alignItems: "center",
              gap: 5,
              fontWeight: 800,
              fontSize: 20,
              color: colors.textPrimary,
              marginBottom: 14,
              fontFamily: "'Poppins', sans-serif",
            }}
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
