/**
 * Hero graphic — the org › project › pod › resources hierarchy with an
 * inherited resource flowing down. Soft rounded cards, à la Shiprocket.
 */
const chip =
  "rounded-xl border border-line bg-card px-3.5 py-2.5 text-sm font-medium text-ink shadow-[0_2px_8px_rgba(20,20,19,0.04)] flex items-center gap-2";

export function HeroDiagram() {
  return (
    <div className="relative">
      <div className="relative rounded-[24px] border border-line bg-surface p-7 shadow-[0_30px_60px_-30px_rgba(115,90,229,0.4)]">
        <div className="relative flex flex-col gap-4">
          {/* Org */}
          <div className="reveal" style={{ animationDelay: "0.1s" }}>
            <div className={`${chip} w-fit border-primary/40 bg-primary-50`}>
              <span className="h-2.5 w-2.5 rounded-full bg-primary" /> ORG · acme
            </div>
          </div>

          <div className="ml-5 h-4 w-px bg-line" />

          {/* Projects */}
          <div className="ml-5 flex flex-wrap gap-3">
            {["project · web", "project · infra"].map((p, i) => (
              <div key={p} className="reveal flex flex-col gap-3" style={{ animationDelay: `${0.25 + i * 0.1}s` }}>
                <div className={chip}>{p}</div>
                <div className="ml-4 flex items-center gap-2">
                  <div className="h-px w-4 bg-line" />
                  <div className={`${chip} bg-surface-2`}>
                    {i === 0 ? "pod · frontend" : "pod · sre"}
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Inherited resource banner */}
          <div
            className="reveal mt-2 flex items-center gap-3 rounded-xl px-4 py-3 text-ink"
            style={{ animationDelay: "0.55s", background: "var(--color-lime)" }}
          >
            <span aria-hidden className="text-base">↳</span>
            <span className="text-sm font-semibold">brand-voice.note — inherited by every pod</span>
          </div>
        </div>
      </div>

      {/* floating resource chip */}
      <div
        className="animate-floaty absolute -right-4 -top-5 hidden rounded-2xl bg-primary px-4 py-3 text-white shadow-[0_18px_40px_-12px_rgba(115,90,229,0.7)] sm:block"
      >
        <span className="text-sm font-semibold">◆ pr-reviewer · v2.4.1</span>
      </div>
    </div>
  );
}
