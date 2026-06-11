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

import type { ApiError } from "../types";

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
