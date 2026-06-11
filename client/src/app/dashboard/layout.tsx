"use client";

/**
 * Dashboard zone (frontend spec §2/§3): auth-guarded, CSR, sidebar layout.
 */

import { Loader2 } from "lucide-react";
import { useRequireAuth } from "@/lib/hooks";
import { useUi } from "@/lib/store";
import { Sidebar, MobileNav } from "@/components/dashboard/Sidebar";
import { TopBar } from "@/components/dashboard/TopBar";
import { CommandPalette } from "@/components/dashboard/CommandPalette";
import { ResourceDrawer } from "@/components/ResourceDrawer";
import { Logo } from "@/components/Logo";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useRequireAuth();
  const { sidebarCollapsed } = useUi();

  if (isLoading || !user) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-surface">
        <Logo className="h-12 w-12 animate-pulse" />
        <p className="flex items-center gap-2 text-sm font-semibold text-muted">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading your workspace…
        </p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-surface">
      <Sidebar />
      <TopBar />
      <CommandPalette />
      <ResourceDrawer />

      <main
        className={`px-4 pb-24 pt-[calc(var(--topbar-h)+1.5rem)] transition-[margin] duration-300 md:px-8 md:pb-12 ${
          sidebarCollapsed ? "md:ml-[var(--sidebar-w-collapsed)]" : "md:ml-[var(--sidebar-w)]"
        }`}
      >
        <div className="mx-auto max-w-6xl">{children}</div>
      </main>

      <MobileNav />
    </div>
  );
}
