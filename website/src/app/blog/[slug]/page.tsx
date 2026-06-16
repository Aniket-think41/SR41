import type { Metadata } from "next";
import { notFound } from "next/navigation";
import Link from "next/link";
import { allPosts, getPost, TAG_STYLE, prettyDate, type Block } from "@/lib/blog";
import { getStarted } from "@/lib/redirects";

export const revalidate = 60;

export async function generateStaticParams() {
  return (await allPosts()).map((p) => ({ slug: p.slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const post = await getPost(slug);
  if (!post) return { title: "Post not found" };
  return {
    title: post.title,
    description: post.excerpt,
    alternates: { canonical: `/blog/${post.slug}` },
    openGraph: {
      title: post.title,
      description: post.excerpt,
      type: "article",
      publishedTime: post.date,
    },
  };
}

function BlockView({ block }: { block: Block }) {
  switch (block.type) {
    case "h2":
      return <h2 className="font-display mt-12 text-2xl font-semibold sm:text-3xl">{block.text}</h2>;
    case "p":
      return <p className="mt-5 text-lg leading-relaxed text-body">{block.text}</p>;
    case "ul":
      return (
        <ul className="mt-5 space-y-2.5">
          {block.items.map((it) => (
            <li key={it} className="flex gap-3 text-lg leading-relaxed text-body">
              <span aria-hidden className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
              <span>{it}</span>
            </li>
          ))}
        </ul>
      );
    case "quote":
      return (
        <blockquote className="mt-8 border-l-[3px] border-primary bg-surface py-5 pl-6 pr-5 rounded-r-2xl">
          <p className="font-display text-xl font-medium text-ink">“{block.text}”</p>
        </blockquote>
      );
  }
}

export default async function BlogPostPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const post = await getPost(slug);
  if (!post) notFound();

  const more = (await allPosts()).filter((p) => p.slug !== post.slug).slice(0, 2);

  return (
    <>
      {/* ============================== HEADER ============================ */}
      <section className="relative overflow-hidden bg-surface">
        <div className="blob right-0 -top-8 h-72 w-72" style={{ background: "var(--color-primary-50)" }} />
        <div className="shell relative py-14 md:py-20">
          <Link href="/blog" className="text-sm font-semibold text-primary link-underline">← Blog</Link>
          <div className="mt-6 flex items-center gap-3">
            <span className={`tag ${TAG_STYLE[post.tag]}`}>{post.tag}</span>
            <span className="text-sm text-muted">{prettyDate(post.date)} · {post.readingMinutes} min read</span>
          </div>
          <h1 className="font-display mt-4 max-w-3xl text-4xl font-semibold leading-tight sm:text-5xl md:text-6xl">
            {post.title}
          </h1>
          {post.standfirst && (
            <p className="mt-5 max-w-2xl text-xl leading-relaxed text-body">{post.standfirst}</p>
          )}
          <div className="mt-7 flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-full bg-primary text-sm font-bold text-white">
              {post.author.name.split(" ").map((w) => w[0]).join("").slice(0, 2)}
            </span>
            <div>
              <p className="text-sm font-semibold text-ink">{post.author.name}</p>
              <p className="text-xs text-muted">{post.author.role}</p>
            </div>
          </div>
        </div>
      </section>

      {/* ============================== BODY ============================== */}
      <article className="shell max-w-3xl py-12 md:py-16">
        {post.body.map((block, i) => (
          <BlockView key={i} block={block} />
        ))}

        <div className="mt-14 flex flex-col items-start gap-4 rounded-[24px] bg-navy p-8 text-white sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="font-display text-2xl font-semibold text-white">Try it on your stack.</h2>
            <p className="mt-1 text-white/70">Free in v1. No card required.</p>
          </div>
          <Link href={getStarted()} className="btn btn-lime shrink-0">Get started free →</Link>
        </div>
      </article>

      {/* ============================= MORE =============================== */}
      {more.length > 0 && (
        <section className="bg-surface">
          <div className="shell py-14 md:py-20">
            <h2 className="kicker">Keep reading</h2>
            <div className="mt-6 grid gap-5 sm:grid-cols-2">
              {more.map((p) => (
                <Link key={p.slug} href={`/blog/${p.slug}`} className="card card-hover group flex flex-col p-6">
                  <div className="flex items-center gap-2">
                    <span className={`tag ${TAG_STYLE[p.tag]}`}>{p.tag}</span>
                    <span className="text-xs text-muted">{p.readingMinutes} min</span>
                  </div>
                  <h3 className="font-display mt-4 text-2xl font-semibold leading-tight transition group-hover:text-primary">
                    {p.title}
                  </h3>
                  <p className="mt-2 line-clamp-2 text-[0.95rem] leading-relaxed text-body">{p.excerpt}</p>
                </Link>
              ))}
            </div>
          </div>
        </section>
      )}
    </>
  );
}
