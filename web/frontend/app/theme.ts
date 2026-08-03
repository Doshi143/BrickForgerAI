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
  hillFar: string;
  hillNear: string;
  treeTrunk: string;
  treeCanopy: string;
  treeCanopyLight: string;
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
  mountainColor: "#26314d",
  hillFar: "#1f3a2c",
  hillNear: "#173123",
  treeTrunk: "#2a1f16",
  treeCanopy: "#254a30",
  treeCanopyLight: "#2f5a3a",
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
  mountainColor: "#b8c9d9",
  hillFar: "#a8c98a",
  hillNear: "#8fb96e",
  treeTrunk: "#7a5233",
  treeCanopy: "#6fa34c",
  treeCanopyLight: "#7fb85c",
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

export const mountains = [
  { w: 70, h: 100 }, { w: 95, h: 150 }, { w: 60, h: 85 }, { w: 105, h: 175 },
  { w: 75, h: 115 }, { w: 90, h: 140 }, { w: 65, h: 95 }, { w: 100, h: 160 },
  { w: 70, h: 105 }, { w: 85, h: 130 }, { w: 60, h: 90 },
];

export const trees = [
  { bottom: "9%", left: "8%", scale: 1 },
  { bottom: "7%", left: "18%", scale: 0.8 },
  { bottom: "10%", left: "72%", scale: 1.1 },
  { bottom: "6%", left: "84%", scale: 0.85 },
  { bottom: "8%", left: "92%", scale: 0.95 },
  { bottom: "11%", left: "3%", scale: 0.75 },
];
