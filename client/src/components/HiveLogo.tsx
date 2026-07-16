/**
 * Hive brand mark — the product's gradient tile (#7C3AED → #4F46E5, rx 7) with a
 * white honeycomb glyph. Rendered as inline SVG so it scales crisply wherever the
 * GitHub icon is used for a provider (integration card grid + config page).
 *
 * The glyph is a clean vector honeycomb (not the raster asset) so it stays sharp
 * at every size; swap in the exact PNG later by replacing the <polygon>s with an
 * <image href="data:image/png;base64,…"> if brand-exactness is required.
 */

const HEXES = [
  "19.5,11 17.75,14.03 14.25,14.03 12.5,11 14.25,7.97 17.75,7.97",
  "15.5,17.2 13.75,20.23 10.25,20.23 8.5,17.2 10.25,14.17 13.75,14.17",
  "23.5,17.2 21.75,20.23 18.25,20.23 16.5,17.2 18.25,14.17 21.75,14.17",
];

export function HiveLogo({ className = "" }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 32 32"
      className={className || "h-6 w-6"}
      role="img"
      aria-label="Hive"
    >
      <defs>
        <linearGradient id="hiveBg" x1="0%" y1="0%" x2="100%" y2="100%" gradientTransform="rotate(-50, 0.5, 0.5)">
          <stop offset="3.67%" stopColor="#7C3AED" />
          <stop offset="96.33%" stopColor="#4F46E5" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="7" fill="url(#hiveBg)" />
      {HEXES.map((pts) => (
        <polygon key={pts} points={pts} fill="#ffffff" opacity="0.95" />
      ))}
    </svg>
  );
}
