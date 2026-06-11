import { redirect } from "next/navigation";

/** The dashboard app's root — the marketing site lives on the website surface. */
export default function Root() {
  redirect("/dashboard");
}
