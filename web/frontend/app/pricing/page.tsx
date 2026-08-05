"use client";

import { useRouter } from "next/navigation";

import Nav from "@/components/Nav";
import Scenery from "@/components/Scenery";
import { useAuth } from "@/components/AuthProvider";
import { useTheme } from "@/components/ThemeProvider";
import { ThemeColors, darkColors, lightColors } from "@/app/theme";

type Plan = {
  id: "free" | "pro";
  name: string;
  price: string;
  priceNote: string;
  credits: string;
  features: string[];
};

const PLANS: Plan[] = [
  {
    id: "free",
    name: "Free",
    price: "£0",
    priceNote: "forever",
    credits: "10 build credits a month",
    features: [
      "10 model generations a month",
      "Full 3D preview with real colors",
      "Instructions + parts list + .ldr download: pay per model, £5–£15 (based on size)",
    ],
  },
  {
    id: "pro",
    name: "Master Builder",
    price: "£25",
    priceNote: "/ month",
    credits: "30 build credits a month",
    features: [
      "30 model generations a month",
      "Full 3D preview with real colors",
      "Instructions + parts list + .ldr download included free on every generation",
    ],
  },
];

export default function PricingPage() {
  const { dark, toggleDark } = useTheme();
  const { user } = useAuth();
  const router = useRouter();

  const colors = dark ? darkColors : lightColors;

  return (
    <div style={{ position: "relative", minHeight: "100vh", background: colors.skyBottom, overflowX: "hidden" }}>
      <Scenery colors={colors} dark={dark} prominence={0.35} />
      <div style={{ position: "relative", zIndex: 2 }}>
        <Nav colors={colors} dark={dark} onToggleDark={toggleDark} />

        <div style={{ maxWidth: 1000, margin: "0 auto", padding: "56px 24px 100px", textAlign: "center" }}>
          <h1 className="display" style={{ fontWeight: 800, fontSize: 40, color: colors.textPrimary, margin: "0 0 12px" }}>
            Simple, credit-based pricing
          </h1>
          <p style={{ color: colors.textSecondary, fontSize: 17, maxWidth: 560, margin: "0 auto 48px" }}>
            Every plan includes full 3D previews with real colors. Instructions and a
            complete parts list are what turn a preview into something buildable.
          </p>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
              gap: 28,
              textAlign: "left",
            }}
          >
            {PLANS.map((plan) => {
              const isCurrent = user?.plan === plan.id;
              return (
                <div
                  key={plan.id}
                  style={{
                    background: colors.cardBg,
                    border: `2px solid ${plan.id === "pro" ? colors.accent : colors.cardBorder}`,
                    borderRadius: 24,
                    padding: 36,
                    position: "relative",
                  }}
                >
                  {plan.id === "pro" && (
                    <div
                      style={{
                        position: "absolute",
                        top: -14,
                        left: 32,
                        background: colors.accent,
                        color: "#fff",
                        fontSize: 12,
                        fontWeight: 700,
                        padding: "4px 12px",
                        borderRadius: 12,
                      }}
                    >
                      Best value
                    </div>
                  )}

                  <div className="display" style={{ fontWeight: 800, fontSize: 22, color: colors.textPrimary, marginBottom: 4 }}>
                    {plan.name}
                  </div>
                  <div style={{ display: "flex", alignItems: "baseline", gap: 6, marginBottom: 6 }}>
                    <span className="display" style={{ fontWeight: 800, fontSize: 40, color: colors.textPrimary }}>
                      {plan.price}
                    </span>
                    <span style={{ color: colors.textSecondary, fontSize: 15 }}>{plan.priceNote}</span>
                  </div>
                  <div style={{ color: colors.accent, fontWeight: 700, fontSize: 15, marginBottom: 24 }}>
                    {plan.credits}
                  </div>

                  <ul style={{ listStyle: "none", padding: 0, margin: "0 0 28px", display: "flex", flexDirection: "column", gap: 12 }}>
                    {plan.features.map((f) => (
                      <li key={f} style={{ display: "flex", gap: 10, color: colors.textPrimary, fontSize: 15, lineHeight: 1.5 }}>
                        <span style={{ color: colors.accent, flexShrink: 0 }}>✓</span>
                        <span>{f}</span>
                      </li>
                    ))}
                  </ul>

                  <button
                    disabled={isCurrent}
                    onClick={() => {
                      if (!user) {
                        router.push(`/signup?next=${encodeURIComponent("/pricing")}`);
                        return;
                      }
                      // Real upgrade requires Stripe, deliberately not wired up
                      // yet -- see web/backend/app/auth.py's module docstring.
                    }}
                    title={user && plan.id === "pro" && !isCurrent ? "Payments aren't wired up yet" : undefined}
                    style={{
                      width: "100%",
                      padding: "14px 20px",
                      borderRadius: 12,
                      border: isCurrent ? `1px solid ${colors.cardBorder}` : "none",
                      background: isCurrent ? "transparent" : colors.accent,
                      color: isCurrent ? colors.textSecondary : "#fff",
                      fontWeight: 700,
                      fontSize: 15,
                      cursor: isCurrent ? "default" : "pointer",
                      fontFamily: "inherit",
                    }}
                  >
                    {isCurrent ? "Your current plan" : !user ? "Sign up free" : "Upgrade (coming soon)"}
                  </button>
                </div>
              );
            })}
          </div>

          <p style={{ color: colors.textSecondary, fontSize: 13, marginTop: 40 }}>
            Payment processing isn&apos;t connected yet — the Free plan is fully live today;
            Master Builder upgrades will be enabled once billing is wired up.
          </p>
        </div>
      </div>
    </div>
  );
}
