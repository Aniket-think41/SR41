import { initials } from "@/lib/utils";

const SIZES = {
  xs: "h-6 w-6 text-[0.6rem]",
  sm: "h-8 w-8 text-[0.7rem]",
  md: "h-10 w-10 text-sm",
  lg: "h-16 w-16 text-xl",
  xl: "h-28 w-28 text-4xl sm:h-36 sm:w-36",
} as const;

/** Deterministic brand-palette background per name. */
const PALETTE = ["#735ae5", "#2f6df0", "#e2552b", "#0a0840", "#15803d", "#b45309"];

export function Avatar({
  name,
  src,
  size = "md",
  className = "",
}: {
  name: string;
  /** when set, render the image; falls back to initials if it's empty/null */
  src?: string | null;
  size?: keyof typeof SIZES;
  className?: string;
}) {
  if (src) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={src}
        alt={name}
        className={`shrink-0 select-none rounded-full object-cover ${SIZES[size]} ${className}`}
      />
    );
  }
  const hue = PALETTE[[...name].reduce((a, c) => a + c.charCodeAt(0), 0) % PALETTE.length];
  return (
    <span
      className={`flex shrink-0 select-none items-center justify-center rounded-full font-bold text-white ${SIZES[size]} ${className}`}
      style={{ backgroundColor: hue }}
      aria-hidden
    >
      {initials(name)}
    </span>
  );
}
