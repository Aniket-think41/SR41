/**
 * Transport seam — THE attach point for the real backend.
 *
 * Today (mock mode): NEXT_PUBLIC_API_URL is unset, every request is
 * dispatched to lib/mock/handlers.ts, which implements the exact REST
 * surface of backend/BACKEND_SPEC.md in the browser.
 *
 * Attach day: set NEXT_PUBLIC_API_URL=https://api.skillshare.think41.com
 * and requests go over the network with the JWT access token attached.
 * No screen, hook, or component changes.
 */

import type { ApiError, Organization, User } from "../types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";
export const USING_MOCK = !API_URL;

const TOKEN_KEY = "skillshare.access_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null) {
  if (typeof window === "undefined") return;
  if (token) window.localStorage.setItem(TOKEN_KEY, token);
  else window.localStorage.removeItem(TOKEN_KEY);
}

export function isApiError(e: unknown): e is ApiError {
  return typeof e === "object" && e !== null && "error" in e;
}

export function errorMessage(e: unknown): string {
  if (isApiError(e)) return e.error.message;
  if (e instanceof Error) return e.message;
  return "Something went wrong";
}

/**
 * Multipart file upload (images / video / diagrams / files). Stored by the
 * backend's switchable storage backend (local disk in dev, S3/R2 in prod),
 * which returns a public file_url. In mock mode there's no server, so we hand
 * back a local object URL so previews still work in the browser.
 */
export async function uploadFile(
  file: File,
  kind: "image" | "video" | "file"
): Promise<{ file_url: string }> {
  if (USING_MOCK) return { file_url: URL.createObjectURL(file) };

  const form = new FormData();
  form.append("file", file);
  form.append("kind", kind);
  const res = await fetch(`${API_URL}/api/uploads`, {
    method: "POST",
    // NB: do NOT set Content-Type — the browser sets the multipart boundary.
    headers: { ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}) },
    body: form,
    credentials: "include",
  });
  if (!res.ok) {
    let err: ApiError;
    try {
      err = (await res.json()) as ApiError;
    } catch {
      err = { error: { code: "INTERNAL_ERROR", message: res.statusText, status: res.status } };
    }
    throw err;
  }
  return (await res.json()) as { file_url: string };
}

/**
 * Upload a new profile picture and get back the updated user. Real mode posts
 * multipart to /api/auth/me/avatar (stored by the switchable storage backend —
 * local disk in dev, S3/R2 in prod). Mock mode has no server, so we make a
 * local object URL and persist it via PATCH so previews work in the browser.
 */
export async function uploadAvatar(file: File): Promise<User> {
  if (USING_MOCK) {
    const { handle } = await import("../mock/handlers");
    return handle("PATCH", "/api/auth/me", { avatar_url: URL.createObjectURL(file) }) as Promise<User>;
  }
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_URL}/api/auth/me/avatar`, {
    method: "POST",
    headers: { ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}) },
    body: form,
    credentials: "include",
  });
  if (!res.ok) {
    let err: ApiError;
    try {
      err = (await res.json()) as ApiError;
    } catch {
      err = { error: { code: "INTERNAL_ERROR", message: res.statusText, status: res.status } };
    }
    throw err;
  }
  return (await res.json()) as User;
}

/** Upload an organization logo (admins only). Same storage path as avatars. */
export async function uploadOrgLogo(slug: string, file: File): Promise<Organization> {
  if (USING_MOCK) {
    const { handle } = await import("../mock/handlers");
    return handle("PATCH", `/api/orgs/${slug}`, { logo_url: URL.createObjectURL(file) }) as Promise<Organization>;
  }
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_URL}/api/orgs/${slug}/logo`, {
    method: "POST",
    headers: { ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}) },
    body: form,
    credentials: "include",
  });
  if (!res.ok) {
    let err: ApiError;
    try {
      err = (await res.json()) as ApiError;
    } catch {
      err = { error: { code: "INTERNAL_ERROR", message: res.statusText, status: res.status } };
    }
    throw err;
  }
  return (await res.json()) as Organization;
}

export async function request<T>(
  method: "GET" | "POST" | "PATCH" | "DELETE",
  path: string,
  body?: unknown
): Promise<T> {
  if (USING_MOCK) {
    const { handle } = await import("../mock/handlers");
    return handle(method, path, body as Record<string, unknown>) as Promise<T>;
  }

  const res = await fetch(`${API_URL}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    credentials: "include", // refresh token cookie (BACKEND SPEC §4.1)
  });

  if (!res.ok) {
    let err: ApiError;
    try {
      err = (await res.json()) as ApiError;
    } catch {
      err = { error: { code: "INTERNAL_ERROR", message: res.statusText, status: res.status } };
    }
    throw err;
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
