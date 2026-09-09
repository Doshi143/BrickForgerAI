/**
 * Color tokens ported verbatim from the design mockup (BrickForge.dc.html's
 * `renderVals()`), so the real app matches the approved visual reference
 * exactly rather than being re-invented by eye.
 */

// Off by default is the SAFE state to ship as -- flip to false any time to
// instantly revert Scenery.tsx (and the nav/footer toggle) to the exact
// original CSS-drawn voxel backdrop and plain 2-state light/dark toggle,
// no other code changes needed. A plain code constant rather than an env
// var, matching this project's own established "commit-driven toggle"
// pattern (see MAINTENANCE_MODE in lib/api.ts) -- flipping it is just a
// commit + push, not a dashboard change.
export const USE_IMAGE_SCENERY = true;

// Same revert pattern as USE_IMAGE_SCENERY above: flip to false any time to
// instantly restore every card/button/input across the whole site to its
// exact original opaque color, no other file needs touching. cardBg,
// cardBorder, inputBorder, ctaBg and badgeBg are shared ThemeColors tokens
// already used by every "box" on the site (homepage, discover, gallery,
// pricing, auth forms, generate results, static pages) -- overriding just
// those 5 values below is what makes the glass look apply everywhere for
// free. glassBlurStyle is the other half: a spreadable style fragment
// (`...glassBlurStyle`) added at each of those box's own JSX so the actual
// frosted blur renders; it collapses to `{}` (a no-op spread) when this
// flag is off, so turning it off reproduces the original pixels exactly,
// not just "close enough."
export const USE_GLASSMORPHISM = true;

export const glassBlurStyle: { backdropFilter?: string; WebkitBackdropFilter?: string } = USE_GLASSMORPHISM
  ? { backdropFilter: "blur(18px)", WebkitBackdropFilter: "blur(18px)" }
  : {};

// AI-generated backdrops (public/scenery/*.webp), one per time of day --
// see ThemeProvider.tsx's SceneryTime state. Only meaningful while
// USE_IMAGE_SCENERY is on.
export const SCENERY_IMAGES: Record<"day" | "evening" | "night", string> = {
  day: "/scenery/day.webp",
  evening: "/scenery/evening.webp",
  night: "/scenery/night.webp",
};

export type ThemeColors = {
  skyTop: string;
  skyBottom: string;
  sunFill: string;
  glow: string;
  craterColor: string;
  cloudColor: string;
  mountainColor: string;
  mountainLit: string;
  mountainFar: string;
  mountainSnow: string;
  hillFar: string;
  hillNear: string;
  treeTrunk: string;
  treeCanopy: string;
  treeCanopyLight: string;
  shrubColor: string;
  shrubColorLight: string;
  rockColor: string;
  birdColor: string;
  gridColor: string;
  navBg: string;
  textPrimary: string;
  textSecondary: string;
  accent: string;
  badgeBg: string;
  cardBg: string;
  cardBorder: string;
  inputBorder: string;
  numColor: string;
  ctaBg: string;
  toggleBg: string;
  heroTextShadow: string;
};

const darkColorsOpaque: ThemeColors = {
  skyTop: "#0b1330",
  skyBottom: "#1a2b52",
  sunFill: "#e8ecf5",
  glow: "rgba(232,236,245,0.35)",
  craterColor: "#a9b3cc",
  cloudColor: "rgba(220,226,240,0.5)",
  mountainColor: "#2c3a5c",
  mountainLit: "#3f5280",
  mountainFar: "#1c2848",
  mountainSnow: "#c9d3ec",
  hillFar: "#1f3a2c",
  hillNear: "#173123",
  treeTrunk: "#2a1f16",
  treeCanopy: "#254a30",
  treeCanopyLight: "#2f5a3a",
  shrubColor: "#1f3d28",
  shrubColorLight: "#2a4e32",
  rockColor: "#3a4560",
  birdColor: "#cfd6e6",
  gridColor: "rgba(255,255,255,0.06)",
  navBg: "rgba(11,19,48,0.7)",
  textPrimary: "#f1f3fa",
  textSecondary: "#a9b3cc",
  accent: "#ef8a4c",
  badgeBg: "rgba(239,138,76,0.15)",
  cardBg: "#141b38",
  cardBorder: "rgba(255,255,255,0.08)",
  inputBorder: "rgba(255,255,255,0.15)",
  numColor: "rgba(239,138,76,0.25)",
  ctaBg: "#0e1530",
  toggleBg: "#2a3560",
  heroTextShadow: "rgba(11,19,48,0.9)",
};

const lightColorsOpaque: ThemeColors = {
  skyTop: "#eaf4fb",
  skyBottom: "#cfe9f7",
  sunFill: "#f5a35c",
  glow: "rgba(245,163,92,0.4)",
  craterColor: "#d98a4a",
  cloudColor: "rgba(255,255,255,0.85)",
  mountainColor: "#a4bcd3",
  mountainLit: "#b9cee0",
  mountainFar: "#cbdcec",
  mountainSnow: "#ffffff",
  hillFar: "#a8c98a",
  hillNear: "#8fb96e",
  treeTrunk: "#7a5233",
  treeCanopy: "#5f9645",
  treeCanopyLight: "#7fb85c",
  shrubColor: "#5f9645",
  shrubColorLight: "#7fb85c",
  rockColor: "#b9b2a2",
  birdColor: "#1e2233",
  gridColor: "rgba(30,30,30,0.06)",
  navBg: "rgba(250,246,240,0.75)",
  textPrimary: "#1a1f36",
  textSecondary: "#6b7690",
  accent: "#e8813a",
  badgeBg: "#fbe4d3",
  cardBg: "#ffffff",
  cardBorder: "#eee0d2",
  inputBorder: "#e4d9cb",
  numColor: "#fbe4d3",
  ctaBg: "#faf6f0",
  toggleBg: "#e4d9cb",
  heroTextShadow: "rgba(255,255,255,0.9)",
};

// Frosted-glass overrides for the 5 "box surface" tokens only -- every
// other token (sky/mountain/text/accent colors etc.) is untouched, since
// this is specifically about card/button/input surfaces, not a full
// re-theme. Applied on top of the opaque bases above rather than as
// separate standalone palettes, so a future edit to e.g. `accent` never
// has to be kept in sync in two places.
export const darkColors: ThemeColors = USE_GLASSMORPHISM
  ? {
      ...darkColorsOpaque,
      badgeBg: "rgba(239,138,76,0.22)",
      cardBg: "rgba(20,27,56,0.35)",
      cardBorder: "rgba(255,255,255,0.22)",
      inputBorder: "rgba(255,255,255,0.3)",
      ctaBg: "rgba(14,21,48,0.35)",
    }
  : darkColorsOpaque;

export const lightColors: ThemeColors = USE_GLASSMORPHISM
  ? {
      ...lightColorsOpaque,
      badgeBg: "rgba(251,228,211,0.45)",
      cardBg: "rgba(255,255,255,0.35)",
      cardBorder: "rgba(255,255,255,0.55)",
      inputBorder: "rgba(255,255,255,0.6)",
      ctaBg: "rgba(255,255,255,0.32)",
    }
  : lightColorsOpaque;

export const clouds = [
  { top: "10%", scale: 1, duration: 55, delay: 0 },
  { top: "24%", scale: 0.75, duration: 70, delay: -20 },
  { top: "4%", scale: 0.9, duration: 60, delay: -40 },
];

export const birds = [
  { top: "20%", duration: 22, delay: 0 },
  { top: "26%", duration: 26, delay: -8 },
  { top: "16%", duration: 30, delay: -16 },
  { top: "23%", duration: 24, delay: -3 },
];

// Twinkling stars (ImageScenery), shown on night and evening -- both have
// a dark-enough upper sky band with a static starfield already baked in;
// day doesn't. Layered on top as a handful of real animated points so the
// sky isn't purely static, without trying to replace the image's own
// starfield. Fixed positions/timings (not Math.random()) so server and
// client render identically and hydration never mismatches.
export const stars = [
  { top: "8%", left: "12%", size: 2, duration: 3.2, delay: 0 },
  { top: "15%", left: "25%", size: 1.5, duration: 4, delay: -1 },
  { top: "6%", left: "40%", size: 2.5, duration: 3.6, delay: -2 },
  { top: "20%", left: "55%", size: 1.5, duration: 4.4, delay: -0.5 },
  { top: "10%", left: "68%", size: 2, duration: 3, delay: -1.5 },
  // Nothing placed in the moon's own top-right region (roughly top 18-36%,
  // left 78-95%, matching where night.webp's own moon sits with the
  // object-position crop Scenery.tsx uses) -- a star drawn on top of the
  // baked-in moon read as a stray mistake, not a real night-sky detail, and
  // was reported as such.
  { top: "14%", left: "5%", size: 1.5, duration: 4.2, delay: -3 },
  { top: "30%", left: "35%", size: 2, duration: 3.4, delay: -1.8 },
  { top: "4%", left: "88%", size: 1.5, duration: 3.9, delay: -0.8 },
  { top: "34%", left: "60%", size: 2, duration: 3.3, delay: -2.2 },
  { top: "28%", left: "15%", size: 1.5, duration: 3.7, delay: -3.4 },
  { top: "22%", left: "48%", size: 2, duration: 3.5, delay: -1.6 },
  { top: "9%", left: "58%", size: 1.5, duration: 4.3, delay: -2.8 },
  { top: "32%", left: "22%", size: 2, duration: 3.1, delay: -0.4 },
  { top: "6%", left: "75%", size: 1.5, duration: 3.85, delay: -1.9 },
];

// peak: 0-100, the % across the mountain's own width where its tip sits --
// varied per mountain (not always 50%) so the ridge line reads as a real,
// irregular range rather than a row of identical symmetric triangles.
// left: 0-100, the row's own horizontal position -- deliberately spaced
// closer than each mountain's own width so adjacent triangles overlap
// (a nearer peak's slope partially covering a neighbor's base), the same
// layered-range look real mountain photos have, instead of a row of
// separate, evenly-gapped cones.
export const mountains = [
  { w: 70, h: 100, peak: 42, left: 1 }, { w: 95, h: 150, peak: 58, left: 7 },
  { w: 60, h: 85, peak: 50, left: 15 }, { w: 105, h: 175, peak: 38, left: 21 },
  { w: 75, h: 115, peak: 55, left: 31 }, { w: 90, h: 140, peak: 46, left: 39 },
  { w: 65, h: 95, peak: 60, left: 49 }, { w: 100, h: 160, peak: 44, left: 56 },
  { w: 70, h: 105, peak: 52, left: 66 }, { w: 85, h: 130, peak: 40, left: 74 },
  { w: 60, h: 90, peak: 56, left: 84 }, { w: 78, h: 120, peak: 48, left: 91 },
];

// A second, smaller/hazier row rendered behind the main ridge for depth --
// fewer peaks, no snow caps (distant enough to read as atmospheric haze).
export const mountainsFar = [
  { w: 55, h: 70, peak: 48, left: 4 }, { w: 80, h: 100, peak: 55, left: 14 },
  { w: 65, h: 82, peak: 40, left: 28 }, { w: 90, h: 115, peak: 52, left: 42 },
  { w: 60, h: 75, peak: 58, left: 58 }, { w: 75, h: 95, peak: 45, left: 70 },
  { w: 70, h: 88, peak: 50, left: 84 },
];

// Low clusters of 3 overlapping blobs plus a small rock -- scattered among
// the trees to break up the empty grass between them.
export const shrubs = [
  { bottom: "6%", left: "13%", scale: 0.9 },
  { bottom: "5%", left: "28%", scale: 0.7 },
  { bottom: "9%", left: "65%", scale: 0.8 },
  { bottom: "7%", left: "78%", scale: 1 },
  { bottom: "5%", left: "97%", scale: 0.65 },
];

export const trees = [
  { bottom: "9%", left: "8%", scale: 1 },
  { bottom: "7%", left: "18%", scale: 0.8 },
  { bottom: "10%", left: "72%", scale: 1.1 },
  { bottom: "6%", left: "84%", scale: 0.85 },
  { bottom: "8%", left: "92%", scale: 0.95 },
  { bottom: "11%", left: "3%", scale: 0.75 },
];
