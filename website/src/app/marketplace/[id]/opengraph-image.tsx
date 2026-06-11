import { ImageResponse } from "next/og";
import { getResource, getPublisher, TYPE_META } from "@/lib/data";

export const size = { width: 1200, height: 630 };
export const contentType = "image/png";
export const alt = "Resource on SkillShare by Think41";

// Generated OG card for each public resource (spec §6).
export default async function Image({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const r = getResource(id);
  const pub = r ? getPublisher(r.publisher) : undefined;

  const WHITE = "#ffffff";
  const INK = "#141413";
  const BODY = "#50504c";
  const PRIMARY = "#735ae5";
  const LIME = "#d1ff00";

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          background: WHITE,
          padding: 72,
          fontFamily: "sans-serif",
          color: INK,
          justifyContent: "space-between",
          backgroundImage:
            "radial-gradient(circle at 88% 8%, rgba(209,255,0,0.28), transparent 38%), radial-gradient(circle at 6% 92%, rgba(115,90,229,0.20), transparent 42%)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <div style={{ width: 44, height: 44, background: PRIMARY, borderRadius: 13, display: "flex" }} />
          <div style={{ fontSize: 32, fontWeight: 700 }}>SkillShare</div>
          <div style={{ fontSize: 22, color: BODY, marginLeft: 4 }}>by Think41</div>
        </div>

        <div style={{ display: "flex", flexDirection: "column" }}>
          <div
            style={{
              display: "flex",
              alignSelf: "flex-start",
              borderRadius: 9999,
              padding: "8px 22px",
              fontSize: 24,
              fontWeight: 600,
              marginBottom: 28,
              background: r?.type === "skill" ? LIME : "#efeafe",
              color: r?.type === "skill" ? INK : PRIMARY,
            }}
          >
            {r ? TYPE_META[r.type].label : "Resource"}
          </div>
          <div style={{ fontSize: 88, fontWeight: 700, lineHeight: 1.02, letterSpacing: -2, maxWidth: 1000, display: "flex" }}>
            {r?.name ?? "Resource not found"}
          </div>
          <div style={{ fontSize: 30, color: BODY, marginTop: 24, maxWidth: 980, display: "flex" }}>
            {r?.summary ?? "Browse the SkillShare marketplace."}
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", borderTop: `1px solid #e9e9f0`, paddingTop: 28 }}>
          <div style={{ fontSize: 26, display: "flex", alignItems: "center", gap: 12 }}>
            <div style={{ width: 40, height: 40, borderRadius: 9999, background: PRIMARY, color: WHITE, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16, fontWeight: 700 }}>
              {pub?.initials ?? "SS"}
            </div>
            {pub?.name ?? "SkillShare"} {pub?.verified ? "✦" : ""}
          </div>
          <div style={{ fontSize: 24, color: BODY, display: "flex" }}>
            {r ? `↓ ${r.installs.toLocaleString()} · ★ ${r.stars}` : ""}
          </div>
        </div>
      </div>
    ),
    { ...size }
  );
}
