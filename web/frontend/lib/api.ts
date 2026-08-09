export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type JobStatus =
  | "queued"
  | "generating_image"
  | "generating_mesh"
  | "building_bricks"
  | "done"
  | "failed";

export type Job = {
  job_id: string;
  prompt: string;
  target_size_studs: number | null;
  created_at: string | null;
  instructions_unlocked: boolean | null;
  instructions_price_gbp: number | null;
  status: JobStatus;
  error: string | null;
  part_count: number | null;
  slope_count: number | null;
  tile_count: number | null;
  color_count: number | null;
  color_source: string | null;
  was_repaired: boolean | null;
  still_critical_count: number | null;
  is_single_piece: boolean | null;
  ldr_download_url: string | null;
  thumbnail_url: string | null;
  has_render: boolean | null;
  is_published: boolean;
};

export type Plan = "free" | "builder" | "pro";

export type AuthUser = {
  id: string;
  email: string;
  plan: Plan;
  credits_remaining: number;
  monthly_credit_allowance: number;
  instructions_included: boolean;
  has_billing_account: boolean;
};

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function _authJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new ApiError(res.status, detail?.detail ?? `Request failed (${res.status})`);
  }
  return res.json();
}

/** source is whatever ?ref=... the visitor first arrived with (see
 * ReferralCapture.tsx), e.g. "reddit-sideproject" -- purely for the
 * founder's own attribution, never shown back to the user. Omitted
 * entirely for a visitor with no captured source rather than sent as
 * null/empty, so the backend can tell "no source" from "empty string"
 * if that distinction ever matters later. */
export function signup(
  email: string,
  password: string,
  source?: string
): Promise<{ token: string; user: AuthUser }> {
  return _authJson("/auth/signup", source ? { email, password, source } : { email, password });
}

export function login(email: string, password: string): Promise<{ token: string; user: AuthUser }> {
  return _authJson("/auth/login", { email, password });
}

/** Always resolves with a generic message, whether or not the email is
 * registered -- the backend deliberately returns the same response
 * either way, so this can't be used to test which emails have accounts. */
export function forgotPassword(email: string): Promise<{ message: string }> {
  return _authJson("/auth/forgot-password", { email });
}

/** Resolves on a successful password change, throws ApiError(400, ...) if
 * the token is invalid/expired/already used -- the caller should send the
 * user back to /forgot-password to request a fresh link in that case. */
export function resetPassword(token: string, newPassword: string): Promise<{ message: string }> {
  return _authJson("/auth/reset-password", { token, new_password: newPassword });
}

export async function fetchMe(token: string): Promise<AuthUser> {
  const res = await fetch(`${API_BASE}/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    throw new ApiError(res.status, "Session expired");
  }
  return res.json();
}

/** Uploads a client-side screenshot of the rendered model as this job's
 * gallery thumbnail (there's no server-side LDraw renderer in this trial
 * app -- see Viewer3D.tsx). Best-effort: failures are swallowed by the
 * caller, since a missing/late thumbnail is cosmetic, not functional. */
export async function saveRender(jobId: string, imageDataUrl: string): Promise<void> {
  await fetch(`${API_BASE}/generate/${jobId}/render`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ image_data_url: imageDataUrl }),
  });
}

/** Returns a Stripe Checkout URL to redirect the browser to -- the
 * instructions unlock is now a real charge, so it no longer unlocks
 * immediately. See generate/[jobId]/page.tsx, which redirects
 * window.location to this URL rather than reading a Job back directly. */
export async function unlockInstructions(jobId: string, token: string): Promise<{ checkout_url: string }> {
  const res = await fetch(`${API_BASE}/generate/${jobId}/unlock-instructions`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new ApiError(res.status, detail?.detail ?? "Failed to start checkout");
  }
  return res.json();
}

/** Free -> Builder/Master Builder, or a change between the two. Returns a
 * Stripe Checkout URL -- the plan change itself happens from the backend's
 * webhook once Stripe confirms payment, not immediately on this call. */
export async function startPlanCheckout(plan: "builder" | "pro", token: string): Promise<{ checkout_url: string }> {
  const res = await fetch(`${API_BASE}/billing/checkout`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ plan }),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new ApiError(res.status, detail?.detail ?? "Failed to start checkout");
  }
  return res.json();
}

/** +5 credits for £6, available to any signed-in user on any plan. */
export async function startTopupCheckout(token: string): Promise<{ checkout_url: string }> {
  const res = await fetch(`${API_BASE}/billing/topup-checkout`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new ApiError(res.status, detail?.detail ?? "Failed to start checkout");
  }
  return res.json();
}

/** Returns a URL to Stripe's own hosted Billing Portal -- next billing
 * date, saved card, invoices, and cancellation (which downgrades to free
 * at the end of the current billing period) are all handled there, not
 * by any page in this app. Only meaningful for a user who has a Stripe
 * customer record at all (see AuthUser.has_billing_account). */
export async function startBillingPortal(token: string): Promise<{ portal_url: string }> {
  const res = await fetch(`${API_BASE}/billing/portal`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new ApiError(res.status, detail?.detail ?? "Failed to open billing portal");
  }
  return res.json();
}

/** Phase labels shown while a job runs. Keys match the backend's JobStatus enum. */
export const STATUS_LABELS: Record<JobStatus, string> = {
  queued: "Queued",
  generating_image: "Imagining your model…",
  generating_mesh: "Sculpting it in 3D…",
  building_bricks: "Laying the bricks…",
  done: "Done",
  failed: "Failed",
};

export const STATUS_ORDER: JobStatus[] = [
  "queued",
  "generating_image",
  "generating_mesh",
  "building_bricks",
  "done",
];

export type BuildSize = "small" | "medium" | "large";

/** Studs along the model's longest horizontal axis. Large is capped
 * deliberately -- part count (and legalize/repair time) grows with this,
 * not just visual size, so "large" stays modest rather than ballooning
 * runtime for a trial app. */
export const SIZE_OPTIONS: { id: BuildSize; label: string; studs: number; hint: string }[] = [
  { id: "small", label: "Small", studs: 15, hint: "Quick, fewer parts" },
  { id: "medium", label: "Medium", studs: 22, hint: "Balanced" },
  { id: "large", label: "Large", studs: 30, hint: "More detail, more parts" },
];

export async function startGeneration(
  prompt: string,
  targetSizeStuds: number,
  token: string
): Promise<{ job_id: string; status: JobStatus; credits_remaining: number }> {
  const res = await fetch(`${API_BASE}/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ prompt, target_size_studs: targetSizeStuds }),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new ApiError(res.status, detail?.detail ?? `Failed to start generation (${res.status})`);
  }
  return res.json();
}

export async function fetchJob(jobId: string): Promise<Job> {
  const res = await fetch(`${API_BASE}/generate/${jobId}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`Failed to fetch job (${res.status})`);
  }
  return res.json();
}

/** Downloads the .ldr file via a real authenticated fetch, not a bare
 * <a href> link -- /generate/{id}/download now requires auth (closing
 * the gap where anyone who knew/guessed a job_id could download a
 * job whose creator had unlocked it -- see main.py::download_ldr's own
 * docstring), and a plain link can't carry an Authorization header.
 * Fetches the bytes, then triggers a save via a temporary object URL. */
export async function downloadLdr(jobId: string, token: string): Promise<void> {
  const res = await fetch(`${API_BASE}/generate/${jobId}/download`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new ApiError(res.status, detail?.detail ?? "Failed to download file");
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${jobId}.ldr`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/** Unrestricted -- used by the 3D viewer to fetch/render the model. The
 * preview itself is free on every plan; downloadUrl (above) is the gated
 * "save the file" action. */
export function previewUrl(jobId: string): string {
  return `${API_BASE}/generate/${jobId}/preview`;
}

export function thumbnailUrl(jobId: string): string {
  return `${API_BASE}/generate/${jobId}/thumbnail`;
}

/** This signed-in user's own completed jobs this calendar month, newest
 * first. Reads from the backend's on-disk job metadata, so it survives a
 * backend restart (unlike the old in-memory-only job store). Requires
 * auth -- the backend scopes results to the caller's own user_id. */
export async function fetchGallery(token: string): Promise<Job[]> {
  const res = await fetch(`${API_BASE}/generate`, {
    cache: "no-store",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch your builds (${res.status})`);
  }
  return res.json();
}

// --- Public gallery (/discover) -- distinct from fetchGallery above,
// which is "My Builds" (the caller's own private job history). These
// are for the public, publish-and-browse gallery instead. ---

export type GalleryCard = {
  job_id: string;
  prompt: string | null;
  published_at: string | null;
  part_count: number | null;
  color_count: number | null;
  thumbnail_url: string | null;
  instructions_price_gbp: number;
};

export type GalleryDetail = GalleryCard & {
  slope_count: number | null;
  tile_count: number | null;
};

/** No auth -- the gallery is browsable while logged out. q is an
 * optional case-insensitive substring search over prompts. */
export async function fetchPublicGallery(q?: string): Promise<GalleryCard[]> {
  const params = q?.trim() ? `?q=${encodeURIComponent(q.trim())}` : "";
  const res = await fetch(`${API_BASE}/gallery${params}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`Failed to load gallery (${res.status})`);
  }
  return res.json();
}

/** No auth -- 404s alike for an unpublished job and a nonexistent one,
 * so this can't be used to probe whether a private job_id exists. */
export async function fetchGalleryItem(jobId: string): Promise<GalleryDetail> {
  const res = await fetch(`${API_BASE}/gallery/${jobId}`, { cache: "no-store" });
  if (!res.ok) {
    throw new ApiError(res.status, res.status === 404 ? "Not found in the gallery" : "Failed to load");
  }
  return res.json();
}

/** Whether the signed-in caller already owns (as creator, or as a paying
 * buyer) this gallery job's download -- lets the detail page show
 * "Download" instead of "Buy" on a return visit, not just right after a
 * checkout redirect. */
export async function fetchGalleryAccess(
  jobId: string,
  token: string
): Promise<{ is_owner: boolean; has_access: boolean }> {
  const res = await fetch(`${API_BASE}/gallery/${jobId}/access`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    throw new ApiError(res.status, "Failed to check access");
  }
  return res.json();
}

export async function publishToGallery(jobId: string, token: string): Promise<{ published: true }> {
  const res = await fetch(`${API_BASE}/gallery/${jobId}/publish`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new ApiError(res.status, detail?.detail ?? "Failed to publish");
  }
  return res.json();
}

export async function unpublishFromGallery(jobId: string, token: string): Promise<{ published: false }> {
  const res = await fetch(`${API_BASE}/gallery/${jobId}/unpublish`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new ApiError(res.status, detail?.detail ?? "Failed to unpublish");
  }
  return res.json();
}

/** A non-creator buying download access to someone else's published
 * gallery build. Returns a Stripe Checkout URL, same pattern as every
 * other checkout function here -- the purchase is only recorded once
 * Stripe's webhook confirms it, not on this call. */
export async function startGalleryPurchaseCheckout(jobId: string, token: string): Promise<{ checkout_url: string }> {
  const res = await fetch(`${API_BASE}/gallery/${jobId}/purchase-checkout`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new ApiError(res.status, detail?.detail ?? "Failed to start checkout");
  }
  return res.json();
}
