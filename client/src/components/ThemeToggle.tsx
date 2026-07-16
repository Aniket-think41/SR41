"use client";

/**
 * Light/dark toggle for the dashboard. The class is applied pre-paint by the
 * inline script in the root layout (no flash); this flips it and persists the
 * choice. Kept in step with the marketing site's toggle so the two feel like
 * one product.
 */

import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";

export function ThemeToggle({ className = "" }: { className?: string }) {
  const [dark, setDark] = useState(false);

  useEffect(() => {
    setDark(document.documentElement.classList.contains("dark"));
  }, []);

  function toggle() {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    try {
      localStorage.setItem("theme", next ? "dark" : "light");
    } catch {
      /* storage disabled — toggle still works for the session */
    }
  }

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
      title={dark ? "Light mode" : "Dark mode"}
      className={`flex h-9 w-9 items-center justify-center rounded-full border border-line text-muted transition hover:border-primary hover:text-primary ${className}`}
    >
      {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
    </button>
  );
}

/** Inline script — run before paint to set the theme class from localStorage /
 *  system preference and avoid a flash of the wrong theme. */
export const THEME_INIT_SCRIPT =
  "(function(){try{var t=localStorage.getItem('theme');" +
  "var d=t==='dark'||(!t&&window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches);" +
  "document.documentElement.classList.toggle('dark',d);}catch(e){}})();";
