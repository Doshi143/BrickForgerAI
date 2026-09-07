/**
 * The BrickForgerAI mark: a 2x2 brick-stud grid, rendered from the real
 * 3D-rendered artwork (public/logo-icon.png) rather than a flat inline SVG.
 * Transparent background, so it sits correctly on both light and dark
 * theme backgrounds without needing a theme-aware recolor.
 */
export default function Logo({ size = 24 }: { size?: number }) {
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src="/logo-icon.png"
      alt=""
      width={size}
      height={size}
      style={{ flexShrink: 0, display: "block" }}
    />
  );
}
