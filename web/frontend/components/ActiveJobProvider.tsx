"use client";

import { createContext, useContext, useEffect, useRef, useState } from "react";

import { Job, fetchJob } from "@/lib/api";

const STORAGE_KEY = "brickforgerai_active_job_id";
const POLL_INTERVAL_MS = 3000;

type ActiveJobContextValue = {
  activeJob: Job | null;
  activeJobId: string | null;
  startTracking: (jobId: string) => void;
  dismiss: () => void;
};

const ActiveJobContext = createContext<ActiveJobContextValue | null>(null);

/** Tracks the most recently started generation job across navigation, so
 * a floating progress/completion bar (see ActiveJobBar) can stay visible
 * while you browse elsewhere in the app. The /generate/[jobId] page's own
 * polling only runs while that exact page is mounted -- without this,
 * navigating away mid-generation meant losing all visibility into it
 * until you manually revisited the URL. Persisted to localStorage (not
 * just React state) so it also survives a full page reload, not only
 * client-side navigation. */
export default function ActiveJobProvider({ children }: { children: React.ReactNode }) {
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [activeJob, setActiveJob] = useState<Job | null>(null);
  const pollTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored) setActiveJobId(stored);
  }, []);

  useEffect(() => {
    if (!activeJobId) {
      setActiveJob(null);
      return;
    }

    let cancelled = false;

    async function poll() {
      try {
        const job = await fetchJob(activeJobId!);
        if (cancelled) return;
        setActiveJob(job);
        // Stop polling once the job reaches a terminal state -- no point
        // hammering the backend for a result that can't change further;
        // the bar just keeps showing the last-known state until the user
        // views or dismisses it.
        if (job.status !== "done" && job.status !== "failed") {
          pollTimer.current = setTimeout(poll, POLL_INTERVAL_MS);
        }
      } catch {
        if (cancelled) return;
        pollTimer.current = setTimeout(poll, POLL_INTERVAL_MS);
      }
    }

    poll();
    return () => {
      cancelled = true;
      clearTimeout(pollTimer.current);
    };
  }, [activeJobId]);

  function startTracking(jobId: string) {
    window.localStorage.setItem(STORAGE_KEY, jobId);
    setActiveJobId(jobId);
  }

  function dismiss() {
    window.localStorage.removeItem(STORAGE_KEY);
    setActiveJobId(null);
    setActiveJob(null);
  }

  return (
    <ActiveJobContext.Provider value={{ activeJob, activeJobId, startTracking, dismiss }}>
      {children}
    </ActiveJobContext.Provider>
  );
}

export function useActiveJob(): ActiveJobContextValue {
  const ctx = useContext(ActiveJobContext);
  if (ctx === null) {
    throw new Error("useActiveJob must be used within <ActiveJobProvider>");
  }
  return ctx;
}
