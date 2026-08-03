"use client";

/**
 * The animated pixel-art backdrop (sun/moon, clouds, birds, mountains,
 * hills, trees) plus the grid overlay, ported from the design mockup so
 * every page sits on the same scene.
 */

import { ThemeColors, birds, clouds, mountains, trees } from "@/app/theme";

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
            <div
              key={`mtn-${i}`}
              style={{
                width: 0,
                height: 0,
                borderLeft: `${m.w}px solid transparent`,
                borderRight: `${m.w}px solid transparent`,
                borderBottom: `${m.h}px solid ${colors.mountainColor}`,
              }}
            />
          ))}
        </div>

        <div style={hill(colors.hillFar, "16%", "scaleX(1.4)", prominence)} />
        <div style={hill(colors.hillNear, "11%", "scaleX(1.4) translateY(20%)", prominence)} />

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
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(5, 6px)",
                gridAutoRows: "6px",
                gap: 1,
                margin: "0 auto",
                justifyContent: "center",
              }}
            >
              <div /><div />
              <div style={{ background: colors.treeCanopy }} />
              <div /><div /><div />
              <div style={{ background: colors.treeCanopyLight }} />
              <div style={{ background: colors.treeCanopy }} />
              <div style={{ background: colors.treeCanopyLight }} />
              <div />
              <div style={{ background: colors.treeCanopy }} />
              <div style={{ background: colors.treeCanopyLight }} />
              <div style={{ background: colors.treeCanopy }} />
              <div style={{ background: colors.treeCanopyLight }} />
              <div style={{ background: colors.treeCanopy }} />
            </div>
            <div
              style={{
                width: 6,
                height: 14,
                background: colors.treeTrunk,
                margin: "0 auto",
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
