import type { Metadata } from "next";
import { getFeedback, initialsOf } from "@/lib/data";
import { FeedbackForm } from "@/components/FeedbackForm";

export const metadata: Metadata = {
  title: "Feedback & testimonials",
  description:
    "What teams say about SkillShare — and a place to share your own. Read approved testimonials and send us your feedback.",
  alternates: { canonical: "/feedback" },
};

export const revalidate = 60;

const Stars = ({ n }: { n: number }) => (
  <span aria-label={`${n} out of 5`} className="text-sm text-primary">
    {"★".repeat(n)}
    <span className="text-line">{"★".repeat(Math.max(0, 5 - n))}</span>
  </span>
);

export default async function FeedbackPage() {
  const items = await getFeedback();

  return (
    <>
      <section className="relative overflow-hidden bg-surface">
        <div className="blob right-0 top-0 h-72 w-72" style={{ background: "var(--color-primary-50)" }} />
        <div className="shell relative py-16 md:py-24">
          <span className="kicker">Feedback</span>
          <h1 className="font-display mt-4 max-w-3xl text-5xl font-semibold sm:text-6xl md:text-[4rem]">
            What teams are saying.
          </h1>
          <p className="mt-5 max-w-xl text-lg text-body">
            Real notes from people building on SkillShare — and a place to add
            yours. We read every one.
          </p>
        </div>
      </section>

      <section className="shell py-14 md:py-20">
        <div className="grid gap-12 lg:grid-cols-[1.3fr_1fr]">
          {/* Testimonials (server-rendered) */}
          <div>
            <h2 className="kicker">Testimonials</h2>
            {items.length > 0 ? (
              <div className="mt-6 grid gap-5 sm:grid-cols-2">
                {items.map((f) => (
                  <article key={f.id} className="card flex h-full flex-col p-6">
                    {f.rating ? <Stars n={f.rating} /> : null}
                    <p className="mt-3 flex-1 text-[0.95rem] leading-relaxed text-body">
                      “{f.message}”
                    </p>
                    <div className="mt-5 flex items-center gap-2.5 border-t border-line pt-4">
                      <span className="flex h-8 w-8 items-center justify-center rounded-full bg-primary text-[0.65rem] font-bold text-white">
                        {initialsOf(f.author)}
                      </span>
                      <div>
                        <div className="text-sm font-medium text-ink">{f.author}</div>
                        {f.category && (
                          <div className="text-xs uppercase tracking-wider text-muted">{f.category}</div>
                        )}
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <p className="mt-6 text-body">No testimonials yet — be the first.</p>
            )}
          </div>

          {/* Submission form (client island) */}
          <div>
            <h2 className="kicker">Share your feedback</h2>
            <div className="mt-6">
              <FeedbackForm />
            </div>
          </div>
        </div>
      </section>
    </>
  );
}
