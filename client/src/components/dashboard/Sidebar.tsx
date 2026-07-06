"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import {
  LayoutDashboard, FolderKanban, Library, Users, Settings,
  Store, LogOut, PanelLeftClose, PanelLeftOpen, UserCircle,
  CreditCard, ShieldCheck, MessagesSquare,
} from "lucide-react";
import { api } from "@/lib/api";
import { useFeature, useSession, useTerms } from "@/lib/hooks";
import { useUi } from "@/lib/store";
import { setToken } from "@/lib/api/http";
import { Logo } from "../Logo";
import { Avatar } from "../Avatar";
import { OrgSwitcher } from "./OrgSwitcher";
import { WorkspaceSwitcher } from "./WorkspaceSwitcher";

/** Nav items per workspace. Org mode = projects/members/RBAC; publisher mode =
 *  just the marketplace + the publisher's own resources (no org/RBAC surfaces).
 *  `label` may be overridden by org terminology; `feature` gates visibility. */
type NavItem = { label: string; href: string; icon: typeof LayoutDashboard; exact?: boolean };

function useNav(): NavItem[] {
  const terms = useTerms();
  const marketplace = useFeature("marketplace");
  const { workspace } = useUi();
  const { data: user } = useSession();

  // Platform-admin surfaces (review queue + feedback moderation), shown in
  // either workspace when the signed-in user is a platform admin (spec §3/§4).
  const adminItems = user?.is_admin
    ? [
        { label: "Review Queue", href: "/dashboard/admin/review", icon: ShieldCheck },
        { label: "Feedback", href: "/dashboard/admin/feedback", icon: MessagesSquare },
      ]
    : [];

  if (workspace === "publisher") {
    return [
      { label: "My Resources", href: "/dashboard/publisher", icon: Library, exact: true },
      { label: "Marketplace", href: "/dashboard/marketplace", icon: Store },
      { label: "Billing", href: "/dashboard/billing", icon: CreditCard },
      ...adminItems,
    ];
  }

  return [
    { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard, exact: true },
    { label: terms.projects, href: "/dashboard/projects", icon: FolderKanban },
    { label: "Org Resources", href: "/dashboard/org/resources", icon: Library },
    ...(marketplace.enabled
      ? [{ label: "Marketplace", href: "/dashboard/marketplace", icon: Store }]
      : []),
    { label: "Members", href: "/dashboard/members", icon: Users },
    { label: "Settings", href: "/dashboard/org/settings", icon: Settings },
    ...adminItems,
  ];
}

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const qc = useQueryClient();
  const { data: user } = useSession();
  const { sidebarCollapsed: collapsed, toggleSidebar, workspace } = useUi();
  const NAV = useNav();

  const logout = async () => {
    await api.logout();
    setToken(null);
    qc.clear();
    router.replace("/login");
  };

  return (
    <aside
      className={`fixed inset-y-0 left-0 z-40 hidden flex-col border-r border-line bg-white transition-[width] duration-300 md:flex ${
        collapsed ? "w-[var(--sidebar-w-collapsed)]" : "w-[var(--sidebar-w)]"
      }`}
    >
      {/* Logo */}
      <div className={`flex h-[var(--topbar-h)] items-center gap-2.5 border-b border-line px-4 ${collapsed ? "justify-center px-0" : ""}`}>
        <Link href="/dashboard" className="flex items-center gap-2.5" aria-label="SkillShare dashboard">
          <Logo className="h-8 w-8 shrink-0" />
          {!collapsed && (
            <span className="font-display text-lg font-semibold tracking-tight">
              Skill<span className="text-primary">Share</span>
            </span>
          )}
        </Link>
      </div>

      {/* Workspace switch (Org ⇆ Publisher) + org switcher (org mode only) */}
      <div className="space-y-2 px-3 pt-4">
        <WorkspaceSwitcher collapsed={collapsed} />
        {workspace === "org" && <OrgSwitcher collapsed={collapsed} />}
      </div>

      {/* Nav */}
      <nav className="mt-4 flex-1 space-y-1 overflow-y-auto px-3">
        {NAV.map(({ label, href, icon: Icon, exact }) => {
          const active = exact ? pathname === href : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={`side-item ${active ? "side-item-active" : ""} ${collapsed ? "justify-center !px-0" : ""}`}
              title={collapsed ? label : undefined}
            >
              <Icon className="h-[18px] w-[18px] shrink-0" />
              {!collapsed && label}
            </Link>
          );
        })}
      </nav>

      {/* Collapse toggle */}
      <button
        onClick={toggleSidebar}
        className={`mx-3 mb-2 flex items-center gap-2 rounded-xl px-3 py-2 text-xs font-semibold text-muted hover:bg-surface hover:text-ink ${collapsed ? "justify-center !px-0" : ""}`}
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
      >
        {collapsed ? <PanelLeftOpen className="h-4 w-4" /> : <><PanelLeftClose className="h-4 w-4" /> Collapse</>}
      </button>

      {/* User */}
      <div className="border-t border-line p-3">
        <div className={`flex items-center gap-2.5 ${collapsed ? "flex-col" : ""}`}>
          <Link href="/dashboard/profile" title="My profile">
            <Avatar name={user?.display_name ?? "?"} src={user?.avatar_url} size="sm" />
          </Link>
          {!collapsed && (
            <>
              <Link href="/dashboard/profile" className="min-w-0 flex-1 hover:opacity-80">
                <span className="block truncate text-sm font-bold text-ink">{user?.display_name}</span>
                <span className="flex items-center gap-1 text-[0.7rem] text-muted">
                  <UserCircle className="h-3 w-3" /> My profile
                </span>
              </Link>
              <button onClick={logout} className="text-muted transition hover:text-[var(--color-danger)]" title="Log out" aria-label="Log out">
                <LogOut className="h-4 w-4" />
              </button>
            </>
          )}
        </div>
      </div>
    </aside>
  );
}

/** Mobile bottom navigation (frontend spec §7, <768px). */
export function MobileNav() {
  const pathname = usePathname();
  const items = useNav().slice(0, 5);
  return (
    <nav className="fixed inset-x-0 bottom-0 z-40 flex border-t border-line bg-white/95 backdrop-blur-md md:hidden">
      {items.map(({ label, href, icon: Icon, exact }) => {
        const active = exact ? pathname === href : pathname.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            className={`flex flex-1 flex-col items-center gap-0.5 py-2.5 text-[0.6rem] font-semibold ${
              active ? "text-primary" : "text-muted"
            }`}
          >
            <Icon className="h-5 w-5" />
            {label.split(" ")[0]}
          </Link>
        );
      })}
    </nav>
  );
}
