/**
 * SkillShare mark — nested rounded squares (org › project › pod hierarchy)
 * with a lime node marking an inherited resource.
 */
export function Logo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden role="presentation">
      <rect x="1" y="1" width="30" height="30" rx="9" fill="var(--color-primary)" />
      <rect x="7" y="7" width="18" height="18" rx="6" fill="none" stroke="#fff" strokeWidth="1.7" opacity="0.9" />
      <rect x="11.5" y="11.5" width="9" height="9" rx="3" fill="none" stroke="#fff" strokeWidth="1.7" />
      <rect x="14" y="14" width="4" height="4" rx="1.2" fill="var(--color-lime)" />
    </svg>
  );
}
