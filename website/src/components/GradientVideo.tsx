/**
 * Looping brand-gradient video backdrop. Self-generated, seamless 8s loop
 * (public/media/gradient.*). Renders behind content via absolute fill — the
 * parent must be `relative overflow-hidden`. Autoplays muted + inline so it
 * works on mobile; the poster paints instantly before the video decodes, and
 * a CSS gradient is the final fallback if neither source loads.
 */
export function GradientVideo({ className = "" }: { className?: string }) {
  return (
    <video
      className={`pointer-events-none absolute inset-0 h-full w-full object-cover ${className}`}
      autoPlay
      loop
      muted
      playsInline
      preload="auto"
      poster="/media/gradient-poster.jpg"
      aria-hidden
      style={{ background: "linear-gradient(120deg, var(--color-primary), var(--color-navy-2))" }}
    >
      <source src="/media/gradient.webm" type="video/webm" />
      <source src="/media/gradient.mp4" type="video/mp4" />
    </video>
  );
}
