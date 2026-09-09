"use client";

/**
 * The scene backdrop every page sits on. Two implementations live here
 * side by side, switched by app/theme.ts's USE_IMAGE_SCENERY flag:
 *
 * - ImageScenery (flag on, current default): the founder's own
 *   AI-generated day/evening/night landscapes (public/scenery/*.webp) as
 *   a static, object-fit:cover backdrop, with the birds/clouds below kept
 *   as real animated overlay layers on top -- motion doesn't need to be
 *   baked into the image, only the (now static) sky/mountains/hills do.
 * - LegacyScenery (flag off): the original animated pixel-art backdrop
 *   (sun/moon, clouds, birds, mountains, hills, trees) ported from the
 *   design mockup, byte-identical to what shipped before this change.
 *
 * Both are kept in full, not one deleted in favor of the other, so
 * reverting is exactly one constant flip + redeploy, never a code rewrite.
 */

import { SceneryTime, useTheme } from "./ThemeProvider";
import {
  SCENERY_IMAGES,
  ThemeColors,
  USE_IMAGE_SCENERY,
  birds,
  clouds,
  mountains,
  mountainsFar,
  shrubs,
  stars,
  trees,
} from "@/app/theme";

export default function Scenery({
  colors,
  dark,
  prominence = 0.5,
}: {
  colors: ThemeColors;
  dark: boolean;
  prominence?: number;
}) {
  return USE_IMAGE_SCENERY ? (
    <ImageScenery colors={colors} dark={dark} prominence={prominence} />
  ) : (
    <LegacyScenery colors={colors} dark={dark} prominence={prominence} />
  );
}

// Birds and clouds read from `dark` (2 states), not `sceneryTime` (3) --
// day and evening both still read as "bright enough for the light-styled
// silhouettes" (dark navy birds, near-white clouds), which holds up fine
// against the warm evening sky too; only night needs the light-colored
// birds/pale-blue clouds the dark palette already provides. Reusing the
// existing 2-value tokens here deliberately avoids inventing a 3rd color
// palette for a distinction that doesn't actually need one.
function ImageScenery({
  colors,
  dark,
  prominence,
}: {
  colors: ThemeColors;
  dark: boolean;
  prominence: number;
}) {
  const { sceneryTime } = useTheme();
  // The illustrated landscapes are far busier than the flat CSS scenery
  // they replace -- real page copy (headings especially) lost contrast
  // sitting directly on top, most noticeably the accent-orange "bricks"
  // span nearly disappearing into the evening image's own orange sky.
  // A soft radial scrim over the upper-middle band (where hero text
  // actually sits) fixes this the standard hero-image way: brighten
  // toward white for dark text (day/evening), darken toward black for
  // light text (night) -- same `dark` split birds/clouds already use.
  const scrimRgb = dark ? "11,19,48" : "255,255,255";
  // Secondary pages (sign-in, static pages, the generate results page) pass
  // a much lower prominence (0.35 vs. the homepage's ~0.5-1) specifically
  // to fade the scene behind form content -- the legacy CSS scenery did
  // this by fading every hand-drawn shape's own opacity, which has no
  // equivalent for a single flat photo. A full-coverage wash toward the
  // same scrim color, scaling inversely with prominence, reproduces the
  // same "less scene, more focus on the content" effect: none of it at
  // prominence=1 (the hero image stays fully vivid), a strong fade at
  // prominence=0.35 (matching how washed-out the old scenery got there).
  const prominenceWash = Math.max(0, (1 - prominence) * 0.75);
  return (
    <>
      <div style={{ position: "fixed", inset: 0, zIndex: 0, overflow: "hidden" }}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          key={sceneryTime}
          src={SCENERY_IMAGES[sceneryTime as SceneryTime]}
          alt=""
          style={{
            position: "absolute",
            inset: 0,
            width: "100%",
            height: "100%",
            objectFit: "cover",
            // Biased toward the lower half so the horizon/mountain band
            // (where all 3 images concentrate their real content) stays in
            // frame on both a wide desktop crop and a tall mobile crop --
            // "cover" alone can just as easily center-crop into empty sky.
            objectPosition: "center 62%",
          }}
        />

        {prominenceWash > 0 && (
          <div
            style={{
              position: "absolute",
              inset: 0,
              background: `rgba(${scrimRgb},${prominenceWash})`,
            }}
          />
        )}

        <div
          style={{
            position: "absolute",
            inset: 0,
            background: `radial-gradient(ellipse 70% 55% at 50% 32%, rgba(${scrimRgb},0.55) 0%, rgba(${scrimRgb},0.22) 55%, rgba(${scrimRgb},0) 100%)`,
          }}
        />

        {sceneryTime === "night" &&
          stars.map((s, i) => (
            <div
              key={`star-${i}`}
              style={{
                position: "absolute",
                top: s.top,
                left: s.left,
                width: s.size,
                height: s.size,
                borderRadius: "50%",
                background: "#ffffff",
                boxShadow: "0 0 4px 1px rgba(255,255,255,0.8)",
                animation: `twinkle ${s.duration}s ease-in-out infinite`,
                animationDelay: `${s.delay}s`,
                opacity: prominence,
              }}
            />
          ))}

        {birds.map((b, i) => (
          <div
            key={`bird-${i}`}
            style={{
              position: "absolute",
              top: b.top,
              left: 0,
              animation: `birdFly ${b.duration}s linear infinite`,
              animationDelay: `${b.delay}s`,
              opacity: prominence * 0.6,
            }}
          >
            <SmoothBird color={colors.birdColor} />
          </div>
        ))}

        {clouds.map((c, i) => (
          <div
            key={`cloud-${i}`}
            style={{
              position: "absolute",
              top: c.top,
              left: 0,
              transform: `scale(${c.scale})`,
              animation: `cloudDrift ${c.duration}s linear infinite`,
              animationDelay: `${c.delay}s`,
              opacity: prominence * 0.85,
            }}
          >
            <SmoothCloud dark={dark} variant={i % CLOUD_VARIANTS.length} />
          </div>
        ))}
      </div>
    </>
  );
}

// Slight per-instance stretch/tilt (applied to the same base silhouette
// below via a wrapping <g> transform) so a row of clouds doesn't read as
// the same puff copy-pasted three times -- "some slight variation in the
// clouds" -- without needing several hand-drawn path variants.
const CLOUD_VARIANTS = [
  { scaleX: 1, scaleY: 1, rotate: 0 },
  { scaleX: 1.14, scaleY: 0.88, rotate: -3 },
  { scaleX: 0.88, scaleY: 1.12, rotate: 3 },
];

const CLOUD_PATH =
  "M25,50 C11,50 0,39 0,29 C0,18 9,10 20,10 C23,4 30,0 39,0 C50,0 59,7 62,17 C74,15 85,23 85,35 C85,44 76,50 66,50 Z";

// A puffy, multi-lobed flat-illustration cloud (SVG, not the legacy pixel
// grid) with a real light-top/shadow-bottom gradient inside the shape --
// "add the shadows that are on the clouds" from the reference images,
// literally, rather than a flat single-color fill. Two fixed gradient
// pairs (not derived from colors.cloudColor) since that token is only
// ever a plain white/pale-blue fill with no shadow tone baked in for
// either theme -- these are new, deliberately chosen to read as "lit
// cream top, soft blue-gray shadow underside" against either sky. A second,
// darker copy of the same silhouette sits behind the main shape, offset
// down-right and scaled slightly smaller, so it peeks out along the
// bottom/trailing edge as a real cast-shadow silhouette -- not just the
// gradient's own internal shading.
function SmoothCloud({ dark, variant = 0 }: { dark: boolean; variant?: number }) {
  const gradId = `cloudGrad${dark ? "Dark" : "Light"}${variant}`;
  const [topStop, bottomStop] = dark
    ? ["rgba(226,232,248,0.65)", "rgba(138,152,188,0.4)"]
    : ["rgba(255,255,255,0.97)", "rgba(196,210,232,0.65)"];
  const shadowColor = dark ? "rgba(60,72,112,0.45)" : "rgba(146,166,196,0.4)";
  const v = CLOUD_VARIANTS[variant % CLOUD_VARIANTS.length];
  return (
    <svg width={100} height={60} viewBox="0 0 100 60" style={{ display: "block", overflow: "visible" }}>
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={topStop} />
          <stop offset="100%" stopColor={bottomStop} />
        </linearGradient>
      </defs>
      <g transform={`translate(42,25) scale(${v.scaleX},${v.scaleY}) rotate(${v.rotate}) translate(-42,-25)`}>
        <path d={CLOUD_PATH} transform="translate(3,5) scale(0.94)" fill={shadowColor} />
        <path d={CLOUD_PATH} fill={`url(#${gradId})`} />
      </g>
    </svg>
  );
}

// A distant bird as two curved wing strokes meeting at a shared root,
// each independently rotating about that root (wingFlapSmoothL/R) --
// reads as a soft "M" silhouette in flight rather than the legacy
// blocky pixel-grid bird, appropriately simple for something this far
// away (real feather/body detail would be invisible at this scale
// regardless of how the shape itself is drawn).
function SmoothBird({ color }: { color: string }) {
  return (
    <svg width={20} height={12} viewBox="0 0 20 12" style={{ display: "block", overflow: "visible" }}>
      <path
        d="M10,10 Q5,4 0,6"
        fill="none"
        stroke={color}
        strokeWidth={1.6}
        strokeLinecap="round"
        style={{ transformOrigin: "10px 10px", animation: "wingFlapSmoothL 0.9s ease-in-out infinite" }}
      />
      <path
        d="M10,10 Q15,4 20,6"
        fill="none"
        stroke={color}
        strokeWidth={1.6}
        strokeLinecap="round"
        style={{ transformOrigin: "10px 10px", animation: "wingFlapSmoothR 0.9s ease-in-out infinite" }}
      />
    </svg>
  );
}

function LegacyScenery({
  colors,
  dark,
  prominence,
}: {
  colors: ThemeColors;
  dark: boolean;
  prominence: number;
}) {
  return (
    <>
      <div
        style={{
          position: "fixed",
          inset: 0,
          zIndex: 0,
          overflow: "hidden",
          background: `linear-gradient(180deg, ${colors.skyTop} 0%, ${colors.skyBottom} 70%)`,
        }}
      >
        <div
          style={{
            position: "absolute",
            top: "18%",
            right: "14%",
            width: 90,
            height: 90,
            borderRadius: "50%",
            background: colors.sunFill,
            boxShadow: `0 0 60px 20px ${colors.glow}`,
            animation: "sunPulse 5s ease-in-out infinite",
          }}
        >
          {dark && (
            <>
              <div style={crater(colors.craterColor, 16, 20, 18)} />
              <div style={crater(colors.craterColor, 10, 50, 55)} />
            </>
          )}
        </div>

        {birds.map((b, i) => (
          <div
            key={`bird-${i}`}
            style={{
              position: "absolute",
              top: b.top,
              left: 0,
              animation: `birdFly ${b.duration}s linear infinite`,
              animationDelay: `${b.delay}s`,
              opacity: prominence * 0.45,
              display: "grid",
              gridTemplateColumns: "repeat(5, 5px)",
              gridTemplateRows: "repeat(3, 5px)",
            }}
          >
            <div style={{ background: colors.birdColor, transformOrigin: "bottom", animation: "wingFlapL 0.7s ease-in-out infinite" }} />
            <div /><div /><div />
            <div style={{ background: colors.birdColor, transformOrigin: "bottom", animation: "wingFlapR 0.7s ease-in-out infinite" }} />
            <div />
            <div style={{ background: colors.birdColor }} />
            <div />
            <div style={{ background: colors.birdColor }} />
            <div /><div /><div />
            <div style={{ background: colors.birdColor }} />
            <div /><div />
          </div>
        ))}

        {clouds.map((c, i) => (
          <div
            key={`cloud-${i}`}
            style={{
              position: "absolute",
              top: c.top,
              left: 0,
              transform: `scale(${c.scale})`,
              animation: `cloudDrift ${c.duration}s linear infinite`,
              animationDelay: `${c.delay}s`,
              opacity: 0.95,
            }}
          >
            <div style={{ display: "grid", gridTemplateColumns: "repeat(8, 15px)", gridTemplateRows: "repeat(3, 15px)" }}>
              {CLOUD_MASK.map((on, j) => (
                <div key={j} style={on ? { background: colors.cloudColor } : undefined} />
              ))}
            </div>
          </div>
        ))}

        <div style={{ position: "absolute", inset: 0, opacity: prominence * 0.7 }}>
          {mountainsFar.map((m, i) => (
            <Mountain
              key={`mtn-far-${i}`}
              m={m}
              color={colors.mountainFar}
              bottom={groundTop(m.left) - 1}
            />
          ))}
        </div>

        <div style={{ position: "absolute", inset: 0, opacity: prominence }}>
          {mountains.map((m, i) => (
            <Mountain
              key={`mtn-${i}`}
              m={m}
              color={colors.mountainColor}
              lit={colors.mountainLit}
              snowColor={colors.mountainSnow}
              bottom={groundTop(m.left) - 3}
            />
          ))}
        </div>

        <div style={hill(mixColor(colors.hillFar, colors.skyBottom, 1 - prominence), "16%", "scaleX(1.4)")} />
        <div style={hill(mixColor(colors.hillNear, colors.skyBottom, 1 - prominence), "11%", "scaleX(1.4) translateY(20%)")} />

        {shrubs.map((s, i) => (
          <div
            key={`shrub-${i}`}
            style={{
              position: "absolute",
              bottom: s.bottom,
              left: s.left,
              opacity: prominence,
              transform: `scale(${s.scale})`,
            }}
          >
            <div style={{ position: "relative", width: 26, height: 14 }}>
              <div style={{ position: "absolute", left: 0, bottom: 0, width: 14, height: 12, borderRadius: "50%", background: colors.shrubColor }} />
              <div style={{ position: "absolute", left: 9, bottom: 2, width: 16, height: 14, borderRadius: "50%", background: colors.shrubColorLight }} />
              <div style={{ position: "absolute", left: 16, bottom: 0, width: 11, height: 10, borderRadius: "50%", background: colors.shrubColor }} />
            </div>
            <div
              style={{
                width: 10,
                height: 5,
                background: colors.rockColor,
                borderRadius: "40% 40% 50% 50%",
                marginLeft: -14,
                opacity: 0.9,
              }}
            />
          </div>
        ))}

        {trees.map((t, i) => (
          <div
            key={`tree-${i}`}
            style={{
              position: "absolute",
              bottom: t.bottom,
              left: t.left,
              opacity: prominence,
              transform: `scale(${t.scale})`,
            }}
          >
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
              <PineTier width={20} height={15} canopy={colors.treeCanopy} highlight={colors.treeCanopyLight} />
              <PineTier width={26} height={16} canopy={colors.treeCanopy} highlight={colors.treeCanopyLight} marginTop={-8} />
              <PineTier width={32} height={17} canopy={colors.treeCanopy} highlight={colors.treeCanopyLight} marginTop={-8} />
            </div>
            <div
              style={{
                width: 6,
                height: 12,
                background: colors.treeTrunk,
                margin: "-1px auto 0",
                boxShadow: "inset -1px 0 0 rgba(0,0,0,0.2)",
              }}
            />
          </div>
        ))}
      </div>

      <div
        style={{
          position: "fixed",
          inset: 0,
          zIndex: 1,
          backgroundImage: `linear-gradient(${colors.gridColor} 1px, transparent 1px), linear-gradient(90deg, ${colors.gridColor} 1px, transparent 1px)`,
          backgroundSize: "48px 48px",
          opacity: 0.5,
          pointerEvents: "none",
        }}
      />
    </>
  );
}

const CLOUD_MASK = [
  0, 0, 1, 1, 1, 0, 0, 0,
  0, 1, 1, 1, 1, 1, 1, 0,
  1, 1, 1, 1, 1, 1, 1, 1,
];

// The real top edge of the grass ground, matching hillFar's own rendered
// ellipse exactly (see hill() below): a 16%-tall dome, stretched by
// scaleX(1.4) around its horizontal center, which widens its effective
// reach to 50 * 1.4 = 70% either side of center. Mountain rows are pinned
// to (and tucked a little below) this exact line so their bases sit flush
// against the ground and rise/fall with its curve, instead of floating
// above it on a flat baseline with a gap of sky showing underneath.
function groundTop(leftPct: number): number {
  const t = Math.min(1, Math.max(-1, (leftPct - 50) / 70));
  return 16 * Math.sqrt(1 - t * t);
}

// A low-poly ridge peak: a single clip-path triangle whose tip sits at
// `peak`% across its own width (not always center), so a row of these
// reads as an irregular mountain range instead of identical cones. `lit`
// overlays a second triangle from the peak to the right edge -- the same
// two-tone technique PineTier uses for its own highlight half -- so each
// mountain reads as lit on the side facing the sun/moon (fixed at the
// scene's upper right in both themes) and shadowed on the other. The snow
// cap is a third shape stacked on top, clipped to the tip; its lower edge
// is a jagged zigzag (see jaggedEdge) rather than a single straight cut,
// and its two ends are still computed to land exactly on the mountain's
// own slanted edges, so it lines up at any width/height/peak combination.
function Mountain({
  m,
  color,
  lit,
  snowColor,
  bottom,
}: {
  m: { w: number; h: number; peak: number; left: number };
  color: string;
  lit?: string;
  snowColor?: string;
  bottom: number;
}) {
  const bodyClip = `polygon(${m.peak}% 0%, 0% 100%, 100% 100%)`;
  const litClip = `polygon(${m.peak}% 0%, ${m.peak}% 100%, 100% 100%)`;
  const snowDepth = 32; // % of height the cap extends down from the tip
  const snowClip = `polygon(${m.peak}% 0%, ${jaggedEdge(m.peak, snowDepth)})`;
  return (
    <div
      style={{
        position: "absolute",
        left: `${m.left}%`,
        bottom: `${bottom}%`,
        transform: "translateX(-50%)",
        width: m.w * 2,
        height: m.h,
      }}
    >
      <div style={{ position: "absolute", inset: 0, background: color, clipPath: bodyClip }} />
      {lit && <div style={{ position: "absolute", inset: 0, background: lit, clipPath: litClip }} />}
      {snowColor && <div style={{ position: "absolute", inset: 0, background: snowColor, clipPath: snowClip }} />}
    </div>
  );
}

// A zigzag path used as the snow cap's own lower boundary -- alternates
// between the full melt depth and a shallower one so the rock/snow line
// reads as jagged and irregular rather than a single straight diagonal
// cut. Each vertex's x is computed from the mountain's own slanted-edge
// bounds AT THAT VERTEX'S OWN Y depth (not lerped between the two
// endpoints' bounds at the full depth) -- the triangle narrows as y
// decreases toward the peak, so reusing the full-depth width for a
// shallower vertex previously pushed it outside the mountain's real edge,
// visibly poking the snow color past the triangle's own silhouette.
function jaggedEdge(peak: number, depth: number): string {
  const teeth = 6;
  const pts: string[] = [];
  for (let i = 0; i <= teeth; i++) {
    const t = i / teeth;
    const y = i % 2 === 0 ? depth : depth * 0.55;
    const xLeft = peak * (1 - y / 100);
    const xRight = peak + (100 - peak) * (y / 100);
    const x = xLeft + (xRight - xLeft) * t;
    pts.push(`${x}% ${y}%`);
  }
  return pts.join(", ");
}

// One tapered, two-tone tier of a stacked low-poly pine tree -- a solid
// "shadow" triangle with a lighter triangle covering just its right half,
// the same faceted-highlight look Mountain's snow cap and the existing
// tree/hill palette already use elsewhere in this scene.
function PineTier({
  width,
  height,
  canopy,
  highlight,
  marginTop = 0,
}: {
  width: number;
  height: number;
  canopy: string;
  highlight: string;
  marginTop?: number;
}) {
  return (
    <div style={{ position: "relative", width, height, marginTop }}>
      <div style={{ position: "absolute", inset: 0, background: canopy, clipPath: "polygon(50% 0%, 0% 100%, 100% 100%)" }} />
      <div style={{ position: "absolute", inset: 0, background: highlight, clipPath: "polygon(50% 0%, 50% 100%, 100% 100%)" }} />
    </div>
  );
}

function crater(color: string, size: number, top: number, left: number): React.CSSProperties {
  return {
    position: "absolute",
    width: size,
    height: size,
    borderRadius: "50%",
    background: color,
    top,
    left,
    opacity: 0.6,
  };
}

function hill(color: string, height: string, transform: string): React.CSSProperties {
  return {
    position: "absolute",
    bottom: 0,
    left: 0,
    right: 0,
    height,
    background: color,
    borderRadius: "50% 50% 0 0 / 100% 100% 0 0",
    transform,
  };
}

// Ground must stay fully opaque -- transparency here is what let mountain
// silhouettes bleed through the grass near its curved top edge (visible as
// a faint triangle ghosted over the hill). Lower-prominence pages (auth
// forms, secondary pages) still want a washed-out ground, so that effect
// is reproduced by blending the real grass color toward the sky instead of
// lowering alpha, which keeps the hill opaque at every prominence level.
function hexToRgb(hex: string): [number, number, number] {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function mixColor(hex: string, towardHex: string, t: number): string {
  const [r1, g1, b1] = hexToRgb(hex);
  const [r2, g2, b2] = hexToRgb(towardHex);
  const r = Math.round(r1 + (r2 - r1) * t);
  const g = Math.round(g1 + (g2 - g1) * t);
  const b = Math.round(b1 + (b2 - b1) * t);
  return `rgb(${r}, ${g}, ${b})`;
}
