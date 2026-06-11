export function SectionHead({
  kicker,
  title,
  intro,
  invert = false,
  center = false,
}: {
  index?: string;
  kicker: string;
  title: React.ReactNode;
  intro?: React.ReactNode;
  invert?: boolean;
  center?: boolean;
}) {
  return (
    <div className={`max-w-3xl ${center ? "mx-auto text-center" : ""}`}>
      <span className={`kicker ${invert ? "!text-lime" : ""}`}>{kicker}</span>
      <h2
        className={`font-display mt-4 text-4xl font-semibold sm:text-5xl md:text-[3.4rem] ${
          invert ? "!text-white" : ""
        }`}
      >
        {title}
      </h2>
      {intro && (
        <p className={`mt-5 text-lg leading-relaxed ${invert ? "text-white/70" : "text-body"}`}>
          {intro}
        </p>
      )}
    </div>
  );
}
