"use client";

/**
 * The animated pixel-art backdrop (sun/moon, clouds, birds, mountains,
 * hills, trees) plus the grid overlay, ported from the design mockup so
 * every page sits on the same scene.
 */

import { ThemeColors, birds, clouds, mountains, mountainsFar, shrubs, trees } from "@/app/theme";

export default function Scenery({
  colors,
  dark,
  prominence = 0.5,
}: {
  colors: ThemeColors;
  dark: boolean;
  prominence?: number;
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
