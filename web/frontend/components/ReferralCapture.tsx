"use client";

import { Suspense, useEffect } from "react";
import { useSearchParams } from "next/navigation";

const STORAGE_KEY = "brickforgerai-signup-source";

/** First-touch attribution: whichever ?ref=... a visitor arrives with
 * first is what sticks, even if they browse around (and pick up a
 * different or absent ?ref=) before actually signing up -- write-once,
 * never overwritten by a later visit. AuthProvider reads this via
 * getStoredSignupSource() when a signup actually happens. */
function ReferralCaptureInner() {
  const searchParams = useSearchParams();

  useEffect(() => {
    const ref = searchParams.get("ref");
    if (ref && !window.localStorage.getItem(STORAGE_KEY)) {
      window.localStorage.setItem(STORAGE_KEY, ref.slice(0, 100));
    }
  }, [searchParams]);

  return null;
}

// useSearchParams() requires its own Suspense boundary to prerender --
// same reasoning as AuthForm.tsx's identical wrapper, see that file's
// comment for the exact build failure this avoids. Mounted once in the
// root layout so it runs on every route, not just the homepage.
export default function ReferralCapture() {
  return (
    <Suspense fallback={null}>
      <ReferralCaptureInner />
    </Suspense>
  );
}

export function getStoredSignupSource(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(STORAGE_KEY);
}
