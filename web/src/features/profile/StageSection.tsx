import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useState } from "react";
import { Card, ErrorState, Loading } from "../../components/States";
import { api, unwrap } from "../../lib/api";

/** The founder's journey stage (spec: Today > Stage; D-78), chosen from the nine. */
export function StageSection({ current }: { current: string | null }) {
  const queryClient = useQueryClient();
  const selectId = useId();
  const [draft, setDraft] = useState("");
  const stages = useQuery({
    queryKey: ["stages"],
    queryFn: async () => unwrap(await api.GET("/stages")),
    staleTime: Infinity,
  });
  const save = useMutation({
    mutationFn: async (stage: string) => unwrap(await api.PUT("/stage", { body: { stage } })),
    onSuccess: async () => {
      setDraft("");
      await queryClient.invalidateQueries();
    },
  });

  const list = stages.data ?? [];
  const position = list.findIndex((s) => s.value === current);
  const now = position >= 0 ? list[position] : undefined;

  return (
    <section id="stage" aria-labelledby="stage-heading" className="flex flex-col gap-3">
      <h2 id="stage-heading" className="m-0 text-xl font-semibold">
        Where you are
      </h2>
      <Card className="flex flex-col gap-3">
        {stages.isPending && <Loading label="Loading the stages…" />}
        {stages.error && <ErrorState error={stages.error} onRetry={() => void stages.refetch()} />}
        {stages.data && (
          <>
            <p className="m-0 text-sm">
              {now ? (
                <>
                  <strong>
                    Stage {position + 1} of {list.length}
                  </strong>{" "}
                  · {now.label}
                </>
              ) : (
                "No stage chosen yet."
              )}
            </p>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (draft) save.mutate(draft);
              }}
              className="flex flex-wrap items-end gap-3"
            >
              <div className="flex flex-col gap-1 text-sm text-ink-muted">
                <label htmlFor={selectId}>{now ? "Change your stage" : "Your stage"}</label>
                <select
                  id={selectId}
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  className="min-h-11 rounded-xl border border-line bg-white px-3 text-ink"
                >
                  <option value="">Choose…</option>
                  {list.map((s, i) => (
                    <option key={s.value} value={s.value}>
                      {i + 1} · {s.label}
                    </option>
                  ))}
                </select>
              </div>
              <button type="submit" className="btn-secondary" disabled={!draft || save.isPending}>
                Save
              </button>
            </form>
          </>
        )}
        {save.error && <ErrorState error={save.error} />}
      </Card>
    </section>
  );
}
