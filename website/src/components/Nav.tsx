"use client";

import Link from "next/link";
import { useState, useEffect } from "react";
import { SITE } from "@/lib/site";
import { getStarted, signIn } from "@/lib/redirects";
import { Logo } from "./Logo";
import { ThemeToggle } from "./ThemeToggle";

export function Nav() {
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : "";
  }, [open]);

  return (
    <header
      className={`sticky top-0 z-50 transition-all duration-300 ${
        scrolled ? "bg-card/85 shadow-[0_4px_24px_-12px_rgba(20,20,19,0.18)] backdrop-blur-xl" : "bg-card"
      }`}
    >
      <div className="shell flex h-20 items-center justify-between">
        <Link href="/home" aria-label="SkillShare home" className="flex items-center gap-2.5">
          <Logo className="h-8 w-8" />
          <span className="font-display text-xl font-semibold tracking-tight">
            Skill<span className="text-primary">Share</span>
          </span>
          <span className="hidden text-xs font-semibold uppercase tracking-wider text-muted sm:inline">
            by {SITE.by}
          </span>
        </Link>

        <nav className="hidden items-center gap-9 md:flex">
          {SITE.nav.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="link-underline text-[0.95rem] font-medium text-body hover:text-ink"
            >
              {item.label}
            </Link>
          ))}
        </nav>

        <div className="hidden items-center gap-3 md:flex">
          <ThemeToggle />
          <Link href={signIn()} className="text-[0.95rem] font-semibold text-ink hover:text-primary">
            Sign in
          </Link>
          <Link href={getStarted()} className="btn btn-primary">
            Get started <span aria-hidden>→</span>
          </Link>
        </div>

        <button
          onClick={() => setOpen((v) => !v)}
          className="flex h-11 w-11 items-center justify-center rounded-full border border-line md:hidden"
          aria-label={open ? "Close menu" : "Open menu"}
          aria-expanded={open}
        >
          <div className="flex flex-col gap-[5px]">
            <span className={`block h-[2px] w-5 bg-ink transition ${open ? "translate-y-[7px] rotate-45" : ""}`} />
            <span className={`block h-[2px] w-5 bg-ink transition ${open ? "opacity-0" : ""}`} />
            <span className={`block h-[2px] w-5 bg-ink transition ${open ? "-translate-y-[7px] -rotate-45" : ""}`} />
          </div>
        </button>
      </div>

      {/* Mobile drawer */}
      {open && (
        <div className="border-t border-line bg-card md:hidden">
          <div className="shell flex flex-col gap-1 py-6">
            {SITE.nav.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setOpen(false)}
                className="font-display py-3 text-3xl"
              >
                {item.label}
              </Link>
            ))}
            <div className="mt-4 flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold text-muted">Appearance</span>
                <ThemeToggle />
              </div>
              <Link href={signIn()} onClick={() => setOpen(false)} className="btn btn-secondary">
                Sign in
              </Link>
              <Link href={getStarted()} onClick={() => setOpen(false)} className="btn btn-primary">
                Get started free →
              </Link>
            </div>
          </div>
        </div>
      )}
    </header>
  );
}
