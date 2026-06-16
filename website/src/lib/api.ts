/**
 * Shared read-only client for the backend's PUBLIC API (`/api/public/*`).
 *
 * When `API_URL` (or `NEXT_PUBLIC_API_URL`) is set, pages fetch live with ISR
 * (revalidate 60s). When it's unset — a standalone marketing build with no
 * backend — callers fall back to their bundled seed content. This mirrors the
 * pattern in lib/data.ts so the whole site degrades the same way.
 */

const API_BASE = (process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, "");

export async function publicGet<T>(path: string): Promise<T | null> {
  if (!API_BASE) return null;
  try {
    const res = await fetch(`${API_BASE}/api/public${path}`, {
      next: { revalidate: 60 },
      headers: { accept: "application/json" },
    });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null; // backend unreachable → caller falls back to bundled seed
  }
}
