import { ThemeColors, USE_GLASSMORPHISM, glassBlurStyle } from "@/app/theme";

/** Shared input styling for every auth-adjacent form (sign in/up, forgot
 * password, reset password) so they stay visually consistent without each
 * one re-declaring the same object. */
export function inputStyle(colors: ThemeColors): React.CSSProperties {
  return {
    padding: "12px 14px",
    borderRadius: 10,
    border: `1px solid ${colors.inputBorder}`,
    // skyBottom is a solid, non-translucent token -- backdropFilter has no
    // visible effect behind an opaque fill, so glass mode swaps in cardBg
    // (already translucent under USE_GLASSMORPHISM) specifically here.
    // Flag off keeps the original skyBottom fill untouched.
    background: USE_GLASSMORPHISM ? colors.cardBg : colors.skyBottom,
    color: colors.textPrimary,
    fontSize: 15,
    outline: "none",
    fontFamily: "inherit",
    ...glassBlurStyle,
  };
}
