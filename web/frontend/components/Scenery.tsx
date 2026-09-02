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
              opacity: prominence,
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

        <div
          style={{
            position: "absolute",
            bottom: "15%",
            left: 0,
            right: 0,
            height: "18%",
            display: "flex",
            alignItems: "flex-end",
            justifyContent: "space-around",
            opacity: prominence * 0.7,
          }}
        >
          {mountainsFar.map((m, i) => (
            <Mountain key={`mtn-far-${i}`} m={m} color={colors.mountainFar} />
          ))}
        </div>

        <div
          style={{
            position: "absolute",
            bottom: "14%",
            left: 0,
            right: 0,
            height: "22%",
            display: "flex",
            alignItems: "flex-end",
            justifyContent: "space-between",
            opacity: prominence,
          }}
        >
          {mountains.map((m, i) => (
            <Mountain key={`mtn-${i}`} m={m} color={colors.mountainColor} snowColor={colors.mountainSnow} />
          ))}
        </div>

        <div style={hill(colors.hillFar, "16%", "scaleX(1.4)", prominence)} />
        <div style={hill(colors.hillNear, "11%", "scaleX(1.4) translateY(20%)", prominence)} />

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

// A low-poly ridge peak: a single clip-path triangle whose tip sits at
// `peak`% across its own width (not always center), so a row of these
// reads as an irregular mountain range instead of identical cones. The
// snow cap is a second triangle stacked on the SAME polygon, clipped to
// just the tip -- its two base corners are computed to fall exactly on
// the mountain's own two slanted edges (see snowClip below), so the cap's
// edges always line up with the peak underneath it, at any width/height/
// peak-offset combination, rather than a fixed-size overlay that only
// looks right by coincidence on some peaks.
function Mountain({ m, color, snowColor }: { m: { w: number; h: number; peak: number }; color: string; snowColor?: string }) {
  const bodyClip = `polygon(${m.peak}% 0%, 0% 100%, 100% 100%)`;
  const snowDepth = 0.32; // fraction of height the cap extends down from the tip
  const leftX = m.peak * (1 - snowDepth);
  const rightX = m.peak + (100 - m.peak) * snowDepth;
  const snowClip = `polygon(${m.peak}% 0%, ${leftX}% ${snowDepth * 100}%, ${rightX}% ${snowDepth * 100}%)`;
  return (
    <div style={{ position: "relative", width: m.w * 2, height: m.h, flexShrink: 0 }}>
      <div style={{ position: "absolute", inset: 0, background: color, clipPath: bodyClip }} />
      {snowColor && <div style={{ position: "absolute", inset: 0, background: snowColor, clipPath: snowClip }} />}
    </div>
  );
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

function hill(color: string, height: string, transform: string, opacity: number): React.CSSProperties {
  return {
    position: "absolute",
    bottom: 0,
    left: 0,
    right: 0,
    height,
    background: color,
    borderRadius: "50% 50% 0 0 / 100% 100% 0 0",
    transform,
    opacity,
  };
}
