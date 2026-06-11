import Link from "next/link";
import { Logo } from "@/components/Logo";

export default function NotFound() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-5 bg-surface px-4 text-center">
      <Logo className="h-12 w-12" />
      <h1 className="font-display text-4xl font-semibold">
        4<span className="hl">0</span>4
      </h1>
      <p className="max-w-sm text-sm text-body">
        That page isn&rsquo;t in the registry. It may have moved scope — or never existed.
      </p>
      <Link href="/dashboard" className="btn btn-primary btn-sm">Back to dashboard</Link>
    </main>
  );
}
