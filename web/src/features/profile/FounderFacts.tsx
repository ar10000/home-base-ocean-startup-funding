import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useId, useState } from "react";
import type { components } from "../../api/schema";
import { Pill } from "../../components/Pill";
import { Card, ErrorState } from "../../components/States";
import { api, unwrap } from "../../lib/api";
import { formatDate } from "../../lib/format";

type FounderFact = components["schemas"]["FounderFactOut"];

// Spec, Founder facts: three optional facts, personal data kept to the minimum a rule needs.
// Each says why it is asked; any can be deleted, and its rules return to Unknown.
const FOUNDER_FIELDS = [
  {
    key: "youngest_founder_birth_date",
    label: "Youngest founder's birth date",
    kind: "date",
    why: "Some calls are only open to founders under a certain age.",
  },
  {
    key: "woman_founder",
    label: "At least one woman founder",
    kind: "yesno",
    why: "Some calls are reserved for teams with a woman founder.",
  },
  {
    key: "woman_ceo",
    label: "Woman CEO",
    kind: "yesno",
    why: "Some calls are reserved for companies led by a woman.",
  },
] as const;

type FounderField = (typeof FOUNDER_FIELDS)[number];

export function FounderFacts({ facts }: { facts: FounderFact[] }) {
  const byKey = new Map(facts.map((f) => [f.key, f]));
  return (
    <section id="founders" aria-labelledby="founders-heading" className="flex flex-col gap-3">
      <div>
        <h2 id="founders-heading" className="m-0 text-xl font-semibold">
          About the founders
        </h2>
        <p className="m-0 mt-1 text-sm text-ink-muted">
          Optional and private: only used to check calls that ask for them, never shared with the
          AI, and you can delete them at any time.
        </p>
      </div>
      <ul className="m-0 flex list-none flex-col gap-3 p-0">
        {FOUNDER_FIELDS.map((field) => (
          <li key={field.key}>
            <FounderFactRow field={field} fact={byKey.get(field.key)} />
          </li>
        ))}
      </ul>
    </section>
  );
}

function shown(field: FounderField, value: FounderFact["value"]): string {
  if (field.kind === "date") return formatDateWithYear(String(value));
  return value === true ? "Yes" : "No";
}

function formatDateWithYear(iso: string): string {
  return `${formatDate(iso)} ${iso.slice(0, 4)}`;
}

function FounderFactRow({ field, fact }: { field: FounderField; fact: FounderFact | undefined }) {
  const queryClient = useQueryClient();
  const inputId = useId();
  const [draft, setDraft] = useState("");
  const path = { key: field.key };
  const refresh = () => queryClient.invalidateQueries();

  const save = useMutation({
    mutationFn: async (value: string | boolean) =>
      unwrap(await api.PUT("/founder-facts/{key}", { params: { path }, body: { value } })),
    onSuccess: async () => {
      setDraft("");
      await refresh();
    },
  });
  const approve = useMutation({
    mutationFn: async () =>
      unwrap(await api.POST("/founder-facts/{key}/approve", { params: { path } })),
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: async () => unwrap(await api.DELETE("/founder-facts/{key}", { params: { path } })),
    onSuccess: refresh,
  });

  const today = new Date().toISOString().slice(0, 10);
  const valid = field.kind === "date" ? draft !== "" && draft <= today : draft !== "";
  const value = field.kind === "date" ? draft : draft === "yes";
  const error = save.error ?? approve.error ?? remove.error;

  return (
    <Card className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="font-semibold">{field.label}</span>
        {fact ? (
          <span className="flex flex-wrap items-center gap-2 text-sm">
            <span>{shown(field, fact.value)}</span>
            {fact.approved ? (
              <Pill tone="confirmed">Approved</Pill>
            ) : (
              <button
                type="button"
                className="btn-primary"
                disabled={approve.isPending}
                onClick={() => approve.mutate()}
              >
                Approve
              </button>
            )}
            <button
              type="button"
              className="btn-secondary"
              disabled={remove.isPending}
              onClick={() => remove.mutate()}
            >
              Delete
            </button>
          </span>
        ) : (
          <Pill tone="unknown">Not given</Pill>
        )}
      </div>
      <p className="m-0 text-xs text-ink-muted">{field.why}</p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (valid) save.mutate(value);
        }}
        className="flex flex-wrap items-end gap-3"
      >
        <div className="flex flex-col gap-1 text-sm text-ink-muted">
          <label htmlFor={inputId}>
            {fact ? `Change: ${field.label.toLowerCase()}` : field.label}
          </label>
          {field.kind === "date" ? (
            <input
              id={inputId}
              type="date"
              max={today}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              className="min-h-11 rounded-xl border border-line bg-white px-3 text-ink"
            />
          ) : (
            <select
              id={inputId}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              className="min-h-11 rounded-xl border border-line bg-white px-3 text-ink"
            >
              <option value="">Choose…</option>
              <option value="yes">Yes</option>
              <option value="no">No</option>
            </select>
          )}
        </div>
        <button type="submit" className="btn-secondary" disabled={!valid || save.isPending}>
          Save
        </button>
      </form>
      {error && <ErrorState error={error} />}
    </Card>
  );
}
