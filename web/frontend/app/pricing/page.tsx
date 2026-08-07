"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";

import Nav from "@/components/Nav";
import Scenery from "@/components/Scenery";
import { useAuth } from "@/components/AuthProvider";
import { useTheme } from "@/components/ThemeProvider";
import { ThemeColors, darkColors, lightColors } from "@/app/theme";
import { ApiError, startPlanCheckout, startTopupCheckout } from "@/lib/api";

type Plan = {
  id: "free" | "builder" | "pro";
  name: string;
  price: string;
  priceNote: string;
  credits: string;
  features: string[];
  badge?: string;
};

const PLANS: Plan[] = [
  {
    id: "free",
    name: "Free",
    price: "£0",
    priceNote: "forever",
    credits: "5 build credits a month",
    features: [
      "5 model generations a month",
      "Full 3D preview with real colors",
      "Instructions + parts list + .ldr download: pay per model, £5–£15 (based on size)",
    ],
  },
  {
    id: "builder",
    name: "Builder",
    price: "£9",
    priceNote: "/ month",
    credits: "12 build credits a month",
    features: [
      "12 model generations a month",
      "Full 3D preview with real colors",
      "Instructions + parts list + .ldr download included free on every generation",
    ],
  },
  {
    id: "pro",
    name: "Master Builder",
    price: "£20",
    priceNote: "/ month",
    credits: "30 build credits a month",
    features: [
      "30 model generations a month",
      "Full 3D preview with real colors",
      "Instructions + parts list + .ldr download included free on every generation",
    ],
    badge: "Best value",
  },
];

function PricingContent() {
  const { dark, toggleDark } = useTheme();
  const { user, token } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [loadingPlan, setLoadingPlan] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const colors = dark ? darkColors : lightColors;
  const checkoutStatus = searchParams.get("checkout");

  async function handleUpgrade(planId: "builder" | "pro") {
    if (!user || !token) {
      router.push(`/signup?next=${encodeURIComponent("/pricing")}`);
      return;
    }
    setError(null);
    setLoadingPlan(planId);
    try {
      const { checkout_url } = await startPlanCheckout(planId, token);
      window.location.href = checkout_url;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't start checkout. Try again.");
      setLoadingPlan(null);
    }
  }

  async function handleTopup() {
    if (!user || !token) {
      router.push(`/signup?next=${encodeURIComponent("/pricing")}`);
      return;
    }
    setError(null);
    setLoadingPlan("topup");
    try {
      const { checkout_url } = await startTopupCheckout(token);
      window.location.href = checkout_url;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't start checkout. Try again.");
      setLoadingPlan(null);
    }
  }

  return (
    <div style={{ position: "relative", minHeight: "100vh", background: colors.skyBottom, overflowX: "hidden" }}>
      <Scenery colors={colors} dark={dark} prominence={0.35} />
      <div style={{ position: "relative", zIndex: 2 }}>
        <Nav colors={colors} dark={dark} onToggleDark={toggleDark} />

        <div style={{ maxWidth: 1100, margin: "0 auto", padding: "56px 24px 100px", textAlign: "center" }}>
          <h1 className="display" style={{ fontWeight: 800, fontSize: 40, color: colors.textPrimary, margin: "0 0 12px" }}>
            Simple, credit-based pricing
          </h1>
          <p style={{ color: colors.textSecondary, fontSize: 17, maxWidth: 560, margin: "0 auto 24px" }}>
            Every plan includes full 3D previews with real colors. Instructions and a
            complete parts list are what turn a preview into something buildable.
          </p>

          {checkoutStatus === "success" && (
            <div
              style={{
                background: colors.cardBg,
                border: `1px solid ${colors.accent}`,
                borderRadius: 14,
                padding: "14px 20px",
                color: colors.textPrimary,
                maxWidth: 480,
                margin: "0 auto 32px",
                fontSize: 14,
              }}
            >
              Payment received — this can take a few seconds to reflect below. Refresh if your
              plan or credits don&apos;t look right yet.
            </div>
          )}
          {checkoutStatus === "cancelled" && (
            <div
              style={{
                background: colors.cardBg,
                border: `1px solid ${colors.cardBorder}`,
                borderRadius: 14,
                padding: "14px 20px",
                color: colors.textSecondary,
                maxWidth: 480,
                margin: "0 auto 32px",
                fontSize: 14,
              }}
            >
              Checkout cancelled — nothing was charged.
            </div>
          )}
          {error && (
            <div
              style={{
                background: colors.cardBg,
                border: "1px solid #ff8f6b",
                borderRadius: 14,
                padding: "14px 20px",
                color: "#ff8f6b",
                maxWidth: 480,
                margin: "0 auto 32px",
                fontSize: 14,
              }}
            >
              {error}
            </div>
          )}

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
              const isPaid = plan.id !== "free";
              return (
                <div
                  key={plan.id}
                  style={{
                    background: colors.cardBg,
                    border: `2px solid ${plan.badge ? colors.accent : colors.cardBorder}`,
                    borderRadius: 24,
                    padding: 36,
                    position: "relative",
                  }}
                >
                  {plan.badge && (
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
                      {plan.badge}
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
                    disabled={isCurrent || (isPaid && loadingPlan === plan.id)}
                    onClick={() => {
                      if (!isPaid) {
                        if (!user) router.push(`/signup?next=${encodeURIComponent("/pricing")}`);
                        return;
                      }
                      handleUpgrade(plan.id as "builder" | "pro");
                    }}
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
                      opacity: isPaid && loadingPlan === plan.id ? 0.6 : 1,
                    }}
                  >
                    {isCurrent
                      ? "Your current plan"
                      : !user
                      ? "Sign up free"
                      : isPaid && loadingPlan === plan.id
                      ? "Redirecting…"
                      : isPaid
                      ? "Upgrade"
                      : "Downgrade to Free"}
                  </button>
                </div>
              );
            })}
          </div>

          {user && (
            <div
              style={{
                marginTop: 40,
                background: colors.cardBg,
                border: `1px solid ${colors.cardBorder}`,
                borderRadius: 20,
                padding: "28px 32px",
                maxWidth: 520,
                margin: "40px auto 0",
                textAlign: "left",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 20,
                flexWrap: "wrap",
              }}
            >
              <div>
                <div className="display" style={{ fontWeight: 700, fontSize: 17, color: colors.textPrimary, marginBottom: 4 }}>
                  Need more credits this month?
                </div>
                <div style={{ color: colors.textSecondary, fontSize: 14 }}>
                  +5 credits for £6, on top of your current plan — no subscription change.
                </div>
              </div>
              <button
                onClick={handleTopup}
                disabled={loadingPlan === "topup"}
                style={{
                  background: "none",
                  border: `2px solid ${colors.accent}`,
                  color: colors.accent,
                  padding: "12px 22px",
                  borderRadius: 12,
                  fontWeight: 700,
                  fontSize: 14,
                  cursor: "pointer",
                  fontFamily: "inherit",
                  whiteSpace: "nowrap",
                  opacity: loadingPlan === "topup" ? 0.6 : 1,
                }}
              >
                {loadingPlan === "topup" ? "Redirecting…" : "Buy +5 credits — £6"}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function PricingPage() {
  return (
    <Suspense fallback={null}>
      <PricingContent />
    </Suspense>
  );
}
