import type { Metadata } from "next";
import { ActivateShell } from "@/components/ActivateShell";

export const metadata: Metadata = { title: "Connect a device" };

export default function ActivatePage() {
  return <ActivateShell />;
}
