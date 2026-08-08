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
};

export type Plan = "free" | "builder" | "pro";

export type AuthUser = {
  id: string;
  email: string;
  plan: Plan;
  credits_remaining: number;
  monthly_credit_allowance: number;
  instructions_included: boolean;
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

export function signup(email: string, password: string): Promise<{ token: string; user: AuthUser }> {
  return _authJson("/auth/signup", { email, password });
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

export function downloadUrl(jobId: string): string {
  return `${API_BASE}/generate/${jobId}/download`;
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
