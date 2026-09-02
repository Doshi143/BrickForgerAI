/**
 * Color tokens ported verbatim from the design mockup (BrickForge.dc.html's
 * `renderVals()`), so the real app matches the approved visual reference
 * exactly rather than being re-invented by eye.
 */

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

export const darkColors: ThemeColors = {
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

export const lightColors: ThemeColors = {
  skyTop: "#eaf4fb",
  skyBottom: "#cfe9f7",
  sunFill: "#f5a35c",
  glow: "rgba(245,163,92,0.4)",
  craterColor: "#d98a4a",
  cloudColor: "rgba(255,255,255,0.85)",
  mountainColor: "#a4bcd3",
  mountainLit: "#cfe0ef",
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
