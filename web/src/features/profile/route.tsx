import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useState, type FormEvent } from "react";
import type { components } from "../../api/schema";
import { Pill } from "../../components/Pill";
import { Card, ErrorState, Loading } from "../../components/States";
import { api, unwrap } from "../../lib/api";
import { factLabel, goalLabel, windowLabel } from "../../lib/format";
import { useToday } from "../today/route";
import { FounderFacts } from "./FounderFacts";
import { KnowledgeBase } from "./KnowledgeBase";
import { StageSection } from "./StageSection";

type Fact = components["schemas"]["FactOut"];
type Goal = components["schemas"]["Goal-Input"];
type Window = components["schemas"]["Window"];

// The hard-rule facts (spec: Requirement types; D-47 keys), in the order the spec lists them.
// Every one is chosen from a list, never typed (D-76): country, sector, legal form and
// consortium need from the API's lists (REQ-09, the words the seed files use), the numbers
// from fixed ranges.
export type Option = { value: string | number; label: string };
type Field = { key: string; listed: boolean; options?: Option[] };

const range = (from: number, to: number, label: (n: number) => string): Option[] =>
  Array.from({ length: to - from + 1 }, (_, i) => ({ value: from + i, label: label(from + i) }));

/** Horizon Europe's short definitions of each technology readiness level. */
const TRL_MEANING = [
  "basic principles observed",
  "technology concept formulated",
  "experimental proof of concept",
  "technology validated in the lab",
  "technology validated in a relevant environment",
  "technology demonstrated in a relevant environment",
  "prototype demonstrated in an operational environment",
  "system complete and qualified",
  "actual system proven in an operational environment",
];

export const FIELDS: Field[] = [
  { key: "country", listed: true },
  { key: "sector", listed: true },
  { key: "legal_form", listed: true },
  {
    key: "company_age",
    listed: false,
    options: range(0, 50, (n) =>
      n === 0 ? "Less than 1 year" : n === 1 ? "1 year" : `${n} years`,
    ),
  },
  {
    key: "team_size",
    listed: false,
    options: range(1, 100, (n) => (n === 1 ? "1 person" : `${n} people`)),
  },
  {
    key: "trl",
    listed: false,
    options: range(1, 9, (n) => `TRL ${n} · ${TRL_MEANING[n - 1] ?? ""}`),
  },
  { key: "applicant_form", listed: true },
];

const GOALS: Goal[] = [
  "pilot_or_test_site",
  "non_dilutive_funding",
  "accelerator_place",
  "first_customers",
  "investment",
];
const WINDOWS: Window[] = ["now", "soon", "later"];

/** Spec: a fact's label records where it came from (D-48). */
const sourceLabel: Record<Fact["label"], string> = {
  sourced: "Sourced",
  user_provided: "Entered by you",
  ai_suggested: "AI suggested",
  unverified: "Unverified",
};

const profileKey = ["profile"] as const;

export function Component() {
  const profile = useQuery({
    queryKey: profileKey,
    queryFn: async () => unwrap(await api.GET("/profile")),
  });
  return (
    <>
      <header>
        <h1 className="m-0 text-4xl font-semibold tracking-tight">Profile</h1>
        <p className="m-0 mt-2 text-sm text-ink-muted">
          Matches and drafts only use facts you have approved.
        </p>
      </header>
      {profile.isPending && <Loading label="Loading your profile…" />}
      {profile.error && <ErrorState error={profile.error} onRetry={() => void profile.refetch()} />}
      {profile.data && <StageSection current={profile.data.stage} />}
      {profile.data && <Facts facts={profile.data.facts} />}
      {profile.data && <KnowledgeBase facts={profile.data.facts} />}
      <Goals />
      {profile.data && <FounderFacts facts={profile.data.founder_facts} />}
    </>
  );
}

function Facts({ facts }: { facts: Fact[] }) {
  const byKey = new Map(facts.map((f) => [f.key, f]));
  const listed = useQuery({
    queryKey: ["fact-options"],
    queryFn: async () => unwrap(await api.GET("/fact-options")),
    staleTime: Infinity,
  });
  return (
    <section id="facts" aria-labelledby="facts-heading" className="flex flex-col gap-3">
      <h2 id="facts-heading" className="m-0 text-xl font-semibold">
        Company facts
      </h2>
      {listed.isPending && <Loading label="Loading the choices…" />}
      {listed.error && <ErrorState error={listed.error} onRetry={() => void listed.refetch()} />}
      {listed.data && (
        <ul className="m-0 flex list-none flex-col gap-3 p-0">
          {FIELDS.map((field) => (
            <li key={field.key}>
              <FactRow
                field={field}
                options={field.listed ? (listed.data[field.key] ?? []) : (field.options ?? [])}
                fact={byKey.get(field.key)}
              />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function shown(options: Option[], value: Fact["value"]): string {
  return options.find((o) => o.value === value)?.label ?? String(value);
}

export function FactRow({
  field,
  options,
  fact,
}: {
  field: Field;
  options: Option[];
  fact: Fact | undefined;
}) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState("");
  const inputId = useId();
  const refresh = () => queryClient.invalidateQueries();

  const save = useMutation({
    mutationFn: async (value: string | number) =>
      unwrap(await api.POST("/facts", { body: { key: field.key, value, label: "user_provided" } })),
    onSuccess: async () => {
      setDraft("");
      await refresh();
    },
  });
  const approve = useMutation({
    mutationFn: async (id: string) =>
      unwrap(
        await api.POST("/facts/{version_id}/approve", { params: { path: { version_id: id } } }),
      ),
    onSuccess: refresh,
  });

  const name = factLabel(field.key);
  const label = name.charAt(0).toUpperCase() + name.slice(1);
  const chosen = options.find((o) => String(o.value) === draft);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (chosen) save.mutate(chosen.value);
  }

  return (
    <Card className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="font-semibold">{label}</span>
        {fact ? (
          <span className="flex flex-wrap items-center gap-2 text-sm">
            <span>{shown(options, fact.value)}</span>
            <Pill tone="unknown">{sourceLabel[fact.label]}</Pill>
            {fact.approved ? (
              <Pill tone="confirmed">Approved</Pill>
            ) : (
              <button
                type="button"
                className="btn-primary"
                disabled={approve.isPending}
                onClick={() => approve.mutate(fact.id)}
              >
                Approve
              </button>
            )}
          </span>
        ) : (
          <Pill tone="unknown">Not given yet</Pill>
        )}
      </div>
      <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
        <div className="flex min-w-0 flex-col gap-1 text-sm text-ink-muted">
          <label htmlFor={inputId}>{fact ? `New ${name}` : label}</label>
          <select
            id={inputId}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            className="min-h-11 max-w-full rounded-xl border border-line bg-white px-3 text-ink"
          >
            <option value="">Choose…</option>
            {options.map((o) => (
              <option key={String(o.value)} value={String(o.value)}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
        <button type="submit" className="btn-secondary" disabled={!chosen || save.isPending}>
          Save
        </button>
      </form>
      {fact && !fact.approved && (
        <p className="m-0 text-xs text-ink-muted">
          Saved, not approved yet: matching does not use it.
        </p>
      )}
      {(save.error ?? approve.error) && <ErrorState error={save.error ?? approve.error} />}
    </Card>
  );
}

function Goals() {
  const today = useToday();
  const queryClient = useQueryClient();
  const current = new Map(
    (today.data?.current_goal ?? []).map((g) => [g.goal as Goal, g.window as Window]),
  );
  const [chosen, setChosen] = useState<Map<Goal, Window> | null>(null);
  const goals = chosen ?? current;

  const save = useMutation({
    mutationFn: async (list: Map<Goal, Window>) =>
      unwrap(
        await api.PUT("/intent", {
          body: { goals: [...list].map(([goal, window]) => ({ goal, window })) },
        }),
      ),
    onSuccess: async () => {
      setChosen(null);
      await queryClient.invalidateQueries();
    },
  });

  function toggle(goal: Goal, on: boolean) {
    const next = new Map(goals);
    if (on) next.set(goal, next.get(goal) ?? "soon");
    else next.delete(goal);
    setChosen(next);
  }
  function setWindow(goal: Goal, window: Window) {
    setChosen(new Map(goals).set(goal, window));
  }

  // INT-01: an intent has at least one goal.
  const none = goals.size === 0;

  return (
    <section id="goals" aria-labelledby="goals-heading" className="flex flex-col gap-3">
      <h2 id="goals-heading" className="m-0 text-xl font-semibold">
        What you are working towards
      </h2>
      <Card className="flex flex-col gap-3">
        {today.isPending && <Loading label="Loading your goals…" />}
        {GOALS.map((goal) => (
          <div key={goal} className="flex flex-wrap items-center justify-between gap-3">
            <label className="flex min-h-11 items-center gap-3">
              <input
                type="checkbox"
                checked={goals.has(goal)}
                onChange={(e) => toggle(goal, e.target.checked)}
                className="size-5 accent-sea"
              />
              {goalLabel[goal]}
            </label>
            {goals.has(goal) && (
              <label className="flex items-center gap-2 text-sm text-ink-muted">
                When
                <select
                  value={goals.get(goal)}
                  onChange={(e) => setWindow(goal, e.target.value as Window)}
                  className="min-h-11 rounded-full border border-line bg-white px-3 text-ink"
                >
                  {WINDOWS.map((w) => (
                    <option key={w} value={w}>
                      {windowLabel[w]}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </div>
        ))}
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            className="btn-primary"
            disabled={chosen === null || none || save.isPending}
            onClick={() => save.mutate(goals)}
          >
            Save goals
          </button>
          {chosen !== null && none && (
            <span className="text-sm text-ink-muted">Choose at least one goal.</span>
          )}
          {save.isSuccess && chosen === null && (
            <span role="status" className="text-sm text-ink-muted">
              Saved
            </span>
          )}
        </div>
        {save.error && <ErrorState error={save.error} />}
      </Card>
    </section>
  );
}
