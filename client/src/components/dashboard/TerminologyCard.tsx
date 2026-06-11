"use client";

/**
 * Org settings → Terminology: rename Projects / Pods to match how the org
 * works (e.g. pods read as "Teams"). The data model never changes — only
 * the labels users see. Gated by the premium "custom-terminology" flag.
 */

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Lock, Type } from "lucide-react";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/api/http";
import { useCurrentOrg, useFeature } from "@/lib/hooks";
import { useToast } from "../Toast";

const PRESETS = [
  { label: "Projects / Pods", project: "Project", pod: "Pod" },
  { label: "Projects / Teams", project: "Project", pod: "Team" },
  { label: "Workstreams / Squads", project: "Workstream", pod: "Squad" },
];

export function TerminologyCard() {
  const { org } = useCurrentOrg();
  const feature = useFeature("custom-terminology");
  const qc = useQueryClient();
  const { toast } = useToast();

  const [project, setProject] = useState("");
  const [pod, setPod] = useState("");
  // hydrate when the (possibly switched) org loads — render-time adjust
  const [loadedOrg, setLoadedOrg] = useState<string | null>(null);
  if (org && org.id !== loadedOrg) {
    setLoadedOrg(org.id);
    setProject(org.terminology?.project ?? "Project");
    setPod(org.terminology?.pod ?? "Pod");
  }

  const isAdmin = org?.my_role === "ADMIN";

  const saveMut = useMutation({
    mutationFn: () =>
      api.updateOrg(org!.slug, {
        terminology: { project: project.trim() || "Project", pod: pod.trim() || "Pod" },
      }),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["orgs"] });
      await qc.invalidateQueries({ queryKey: ["org", org!.slug] });
      toast("Terminology updated — the whole dashboard now uses your labels");
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  const locked = !feature.enabled;

  return (
    <div className="card p-6">
      <div className="flex items-center justify-between">
        <h2 className="font-display flex items-center gap-2 text-lg font-semibold">
          <Type className="h-4 w-4 text-primary" /> Terminology
        </h2>
        <span className="tag !bg-lime !text-ink">Premium</span>
      </div>
      <p className="mt-1 text-sm text-body">
        Call things what your org calls them — many teams read a pod as a{" "}
        <span className="font-bold text-ink">Team</span>. URLs and the API stay unchanged.
      </p>

      {locked ? (
        <p className="mt-4 flex items-center gap-2 rounded-2xl border border-dashed border-line bg-surface p-4 text-sm text-muted">
          <Lock className="h-4 w-4 shrink-0" />
          {feature.licensed
            ? "Custom terminology is disabled — enable it in Features above."
            : "Custom terminology needs a premium license — activate one in Features above."}
        </p>
      ) : (
        <>
          <div className="mt-4 flex flex-wrap gap-2">
            {PRESETS.map((p) => {
              const active = p.project === project && p.pod === pod;
              return (
                <button
                  key={p.label}
                  onClick={() => {
                    setProject(p.project);
                    setPod(p.pod);
                  }}
                  className={`pill !py-1.5 text-xs ${active ? "pill-active" : ""}`}
                  disabled={!isAdmin}
                >
                  {p.label}
                </button>
              );
            })}
          </div>

          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <div>
              <label className="field-label" htmlFor="term-project">“Project” becomes</label>
              <input
                id="term-project"
                value={project}
                onChange={(e) => setProject(e.target.value)}
                className="field"
                disabled={!isAdmin}
              />
            </div>
            <div>
              <label className="field-label" htmlFor="term-pod">“Pod” becomes</label>
              <input
                id="term-pod"
                value={pod}
                onChange={(e) => setPod(e.target.value)}
                className="field"
                disabled={!isAdmin}
              />
            </div>
          </div>

          {isAdmin && (
            <button
              onClick={() => saveMut.mutate()}
              disabled={saveMut.isPending || !project.trim() || !pod.trim()}
              className="btn btn-primary btn-sm mt-4"
            >
              {saveMut.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              Save terminology
            </button>
          )}
        </>
      )}
    </div>
  );
}
