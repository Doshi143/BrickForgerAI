import { ThemeColors } from "@/app/theme";

/** Shared input styling for every auth-adjacent form (sign in/up, forgot
 * password, reset password) so they stay visually consistent without each
 * one re-declaring the same object. */
export function inputStyle(colors: ThemeColors): React.CSSProperties {
  return {
    padding: "12px 14px",
    borderRadius: 10,
    border: `1px solid ${colors.inputBorder}`,
    background: colors.skyBottom,
    color: colors.textPrimary,
    fontSize: 15,
    outline: "none",
    fontFamily: "inherit",
  };
}
