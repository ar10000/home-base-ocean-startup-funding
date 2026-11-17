import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useId, useState, type FormEvent } from "react";
import type { components } from "../../api/schema";
import { Pill } from "../../components/Pill";
import { Card, ErrorState } from "../../components/States";
import { api, unwrap } from "../../lib/api";

type Fact = components["schemas"]["FactOut"];

// D-80: the knowledge base, four facts from the spec's own list, written as prose.
// Drafts retrieve from them once approved (D-81); matching never reads them.
export const KNOWLEDGE: { key: string; title: string; hint: string }[] = [
  {
    key: "description",
    title: "What the company does",
    hint: "One or two sentences a funder outside your field would understand.",
  },
  {
    key: "impact",
    title: "Impact",
    hint: "What changes for the ocean or the coast, with figures and where they come from.",
  },
  {
    key: "team",
    title: "Team",
    hint: "Who the founders are and what each one brings.",
  },
  {
    key: "traction",
    title: "Traction",
    hint: "Pilots, customers, partners, revenue, grants won, with dates.",
  },
];

export function KnowledgeBase({ facts }: { facts: Fact[] }) {
  const byKey = new Map(facts.map((f) => [f.key, f]));
  return (
    <section id="knowledge" aria-labelledby="knowledge-heading" className="flex flex-col gap-3">
      <div>
        <h2 id="knowledge-heading" className="m-0 text-xl font-semibold">
          About your company
        </h2>
        <p className="m-0 mt-1 text-sm text-ink-muted">
          Written once, reused in every application. AI drafts only quote what you approve here.
        </p>
      </div>
      <ul className="m-0 flex list-none flex-col gap-3 p-0">
        {KNOWLEDGE.map((k) => (
          <li key={k.key}>
            <KnowledgeFact entry={k} fact={byKey.get(k.key)} />
          </li>
        ))}
      </ul>
    </section>
  );
}

function KnowledgeFact({
  entry,
  fact,
}: {
  entry: (typeof KNOWLEDGE)[number];
  fact: Fact | undefined;
}) {
  const queryClient = useQueryClient();
  const current = typeof fact?.value === "string" ? fact.value : "";
  const [text, setText] = useState(current);
  const id = useId();
  const refresh = () => queryClient.invalidateQueries();

  const save = useMutation({
    mutationFn: async (value: string) =>
      unwrap(await api.POST("/facts", { body: { key: entry.key, value, label: "user_provided" } })),
    onSuccess: refresh,
  });
  const approve = useMutation({
    mutationFn: async (versionId: string) =>
      unwrap(
        await api.POST("/facts/{version_id}/approve", {
          params: { path: { version_id: versionId } },
        }),
      ),
    onSuccess: refresh,
  });

  const changed = text.trim() !== "" && text.trim() !== current;

  function submit(event: FormEvent) {
    event.preventDefault();
    if (changed) save.mutate(text.trim());
  }

  return (
    <Card className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <label htmlFor={id} className="font-semibold">
          {entry.title}
        </label>
        {fact ? (
          fact.approved ? (
            <Pill tone="confirmed">Approved</Pill>
          ) : (
            <span className="flex items-center gap-2">
              <Pill tone="unknown">Not approved yet</Pill>
              <button
                type="button"
                className="btn-primary"
                disabled={approve.isPending || changed}
                onClick={() => approve.mutate(fact.id)}
              >
                Approve
              </button>
            </span>
          )
        ) : (
          <Pill tone="unknown">Not given yet</Pill>
        )}
      </div>
      <form onSubmit={submit} className="flex flex-col gap-3">
        <textarea
          id={id}
          rows={3}
          value={text}
          onChange={(e) => setText(e.target.value)}
          aria-describedby={`${id}-hint`}
          className="rounded-xl border border-line bg-white p-3 font-sans text-base text-ink"
        />
        <p id={`${id}-hint`} className="m-0 text-xs text-ink-muted">
          {entry.hint}
        </p>
        <button
          type="submit"
          className="btn-secondary self-start"
          disabled={!changed || save.isPending}
        >
          {save.isPending ? "Saving…" : "Save"}
        </button>
      </form>
      {(save.error ?? approve.error) && <ErrorState error={save.error ?? approve.error} />}
    </Card>
  );
}
