import { ThemeColors } from "@/app/theme";

/**
 * The BrickForgerAI mark: a 2x2 brick-stud grid. The two diagonal cells
 * carry the "B" / "F" initials; the two off-diagonal cells each show a
 * small circular stud, so it still reads as a brick even with letters on it.
 */
export default function Logo({ colors, size = 24 }: { colors: ThemeColors; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" style={{ flexShrink: 0 }} aria-hidden="true">
      <rect x="0" y="0" width="11" height="11" rx="2" fill={colors.accent} />
      <text
        x="5.5"
        y="5.7"
        fontSize="8"
        fontWeight={800}
        fill="#fff"
        textAnchor="middle"
        dominantBaseline="central"
        fontFamily="Poppins, sans-serif"
      >
        B
      </text>

      <rect x="13" y="0" width="11" height="11" rx="2" fill={colors.accent} opacity={0.7} />
      <circle cx="18.5" cy="5.5" r="2.3" fill="#fff" opacity={0.55} />

      <rect x="0" y="13" width="11" height="11" rx="2" fill={colors.accent} opacity={0.7} />
      <circle cx="5.5" cy="18.5" r="2.3" fill="#fff" opacity={0.55} />

      <rect x="13" y="13" width="11" height="11" rx="2" fill={colors.accent} />
      <text
        x="18.5"
        y="18.7"
        fontSize="8"
        fontWeight={800}
        fill="#fff"
        textAnchor="middle"
        dominantBaseline="central"
        fontFamily="Poppins, sans-serif"
      >
        F
      </text>
    </svg>
  );
}
