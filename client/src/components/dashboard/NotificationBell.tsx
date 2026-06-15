"use client";

/**
 * Notification bell (F1) — unread badge + dropdown of resources added or
 * published in scopes the user belongs to. Each row deep-links into the
 * resource and offers the CLI install command. Feature-gated by "notifications".
 */

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, Check, Sparkles, Globe } from "lucide-react";
import { api } from "@/lib/api";
import { qk, useFeature } from "@/lib/hooks";
import { timeAgo } from "@/lib/utils";
import { Avatar } from "../Avatar";

export function NotificationBell() {
  const enabled = useFeature("notifications").enabled;
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const router = useRouter();
  const qc = useQueryClient();

  const { data: unread } = useQuery({
    queryKey: qk.notificationsUnread,
    queryFn: () => api.notificationsUnreadCount(),
    enabled,
    refetchInterval: 60_000, // light poll; real-time push is a later phase
  });
  const { data: items } = useQuery({
    queryKey: qk.notifications(false),
    queryFn: () => api.notifications({ limit: 20 }),
    enabled: enabled && open,
  });

  const markRead = useMutation({
    mutationFn: (body: { ids?: string[]; all?: boolean }) => api.markNotificationsRead(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.notificationsUnread });
      qc.invalidateQueries({ queryKey: ["notifications"] });
    },
  });

  // close on outside click
  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  if (!enabled) return null;

  const count = unread?.count ?? 0;

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="relative flex h-9 w-9 items-center justify-center rounded-full border border-line text-muted transition hover:border-primary hover:text-primary"
        aria-label={`Notifications${count ? ` (${count} unread)` : ""}`}
      >
        <Bell className="h-4 w-4" />
        {count > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[0.6rem] font-bold text-white">
            {count > 9 ? "9+" : count}
          </span>
        )}
      </button>

      {open && (
        <div className="drawer-panel absolute right-0 top-11 z-50 w-[min(22rem,calc(100vw-2rem))] overflow-hidden rounded-2xl border border-line bg-white shadow-[0_24px_64px_-24px_rgba(10,8,64,0.4)]">
          <div className="flex items-center justify-between border-b border-line px-4 py-3">
            <h3 className="font-display text-sm font-bold">Notifications</h3>
            {count > 0 && (
              <button
                onClick={() => markRead.mutate({ all: true })}
                className="flex items-center gap-1 text-xs font-bold text-primary hover:underline"
              >
                <Check className="h-3 w-3" /> Mark all read
              </button>
            )}
          </div>

          <div className="thin-scroll max-h-[60vh] overflow-y-auto">
            {(items ?? []).length === 0 && (
              <p className="px-4 py-10 text-center text-sm text-muted">You&rsquo;re all caught up.</p>
            )}
            {(items ?? []).map((n) => (
              <button
                key={n.id}
                onClick={() => {
                  if (!n.read_at) markRead.mutate({ ids: [n.id] });
                  if (n.deep_link) router.push(n.deep_link);
                  setOpen(false);
                }}
                className={`flex w-full items-start gap-3 border-b border-line/60 px-4 py-3 text-left transition hover:bg-surface ${
                  n.read_at ? "" : "bg-primary-50/40"
                }`}
              >
                <Avatar name={n.actor?.display_name ?? "?"} size="xs" className="mt-0.5 shrink-0" />
                <span className="min-w-0 flex-1">
                  <span className="block text-sm leading-snug">
                    <span className="font-bold text-ink">{n.actor?.display_name ?? "Someone"}</span>{" "}
                    <span className="text-body">{n.verb === "published" ? "published" : "added"}</span>{" "}
                    <span className="font-semibold text-primary">{n.object_title}</span>
                  </span>
                  <span className="mt-0.5 flex items-center gap-1.5 text-xs text-muted">
                    {n.verb === "published" ? <Globe className="h-3 w-3" /> : <Sparkles className="h-3 w-3" />}
                    {timeAgo(n.created_at)}
                  </span>
                </span>
                {!n.read_at && <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-primary" />}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
