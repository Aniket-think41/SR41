import Link from "next/link";

export default function NotFound() {
  return (
    <section className="relative flex min-h-[70vh] items-center overflow-hidden">
      <div className="blob left-1/2 top-1/4 h-96 w-96 -translate-x-1/2" style={{ background: "var(--color-primary-50)" }} />
      <div className="shell relative text-center">
        <p className="font-display text-[8rem] font-bold leading-none text-primary sm:text-[12rem]">404</p>
        <h1 className="font-display mt-2 text-3xl font-semibold sm:text-4xl">This resource isn&apos;t in the registry.</h1>
        <p className="mx-auto mt-4 max-w-md text-body">
          The page you&apos;re looking for moved or never existed. Try the
          marketplace instead.
        </p>
        <div className="mt-8 flex flex-wrap justify-center gap-3">
          <Link href="/" className="btn btn-primary">Back home →</Link>
          <Link href="/marketplace" className="btn btn-secondary">Browse marketplace</Link>
        </div>
      </div>
    </section>
  );
}
