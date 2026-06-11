"use client";

/**
 * Import landing — the website's "Add to my org" CTA deep-links here
 * (website/src/lib/redirects.ts → /dashboard/import/:id). We resolve the
 * public resource and forward to its in-app marketplace page.
 */

import { use, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";

export default function ImportPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();

  useEffect(() => {
    router.replace(`/dashboard/marketplace/${id}`);
  }, [id, router]);

  return (
    <div className="flex min-h-[50vh] items-center justify-center">
      <p className="flex items-center gap-2 text-sm font-semibold text-muted">
        <Loader2 className="h-4 w-4 animate-spin" /> Opening resource…
      </p>
    </div>
  );
}
