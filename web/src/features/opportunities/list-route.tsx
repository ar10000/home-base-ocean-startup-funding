import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Link, useSearchParams } from "react-router";
import type { components } from "../../api/schema";
import { Pill, type Tone } from "../../components/Pill";
import { Empty, ErrorState, Loading } from "../../components/States";
import { api, unwrap } from "../../lib/api";
import {
  checkedLabel,
  deadlineLabel,
  decisionLabel,
  fitLabel,
  openingLabel,
  readinessLabel,
  scopeLabel,
  typesLabel,
} from "../../lib/format";

type Item = components["schemas"]["OpportunityItem"];
type FitStatus = components["schemas"]["FitStatus"];
type Decision = components["schemas"]["Decision"];

const FITS: FitStatus[] = ["confirmed", "possible", "not_eligible"];
const DECISIONS: Decision[] = ["pursuing", "later", "not_for_us"];

export const fitTone: Record<FitStatus, Tone> = {
  confirmed: "confirmed",
  possible: "unknown",
  not_eligible: "unknown",
};

function parse<T extends string>(value: string | null, allowed: readonly T[]): T | null {
  return allowed.find((a) => a === value) ?? null;
}

export function Component() {
  const [params, setParams] = useSearchParams();
  const fit = parse(params.get("fit"), FITS);
  const decision = parse(params.get("decision"), DECISIONS);

  const list = useQuery({
    queryKey: ["opportunities", { fit, decision }],
    queryFn: async () =>
      unwrap(await api.GET("/opportunities", { params: { query: { fit, decision } } })),
  });

  function setFilter(key: "fit" | "decision", value: string | null) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  }

  const counts = list.data?.counts;
  // "All" is the default list, which leaves out Not eligible (spec: Fit).
  const allCount = counts ? (counts.confirmed ?? 0) + (counts.possible ?? 0) : null;

  return (
    <>
      <header className="flex flex-wrap items-end justify-between gap-4">
        <h1 className="m-0 text-4xl font-semibold tracking-tight">Opportunities</h1>
        <label className="flex items-center gap-2 text-sm text-ink-muted">
          Decision
          <select
            value={decision ?? ""}
            onChange={(e) => setFilter("decision", e.target.value || null)}
            className="min-h-11 rounded-full border border-line bg-white px-3 text-ink"
          >
            <option value="">Any</option>
            {DECISIONS.map((d) => (
              <option key={d} value={d}>
                {decisionLabel[d]}
              </option>
            ))}
          </select>
        </label>
      </header>

      <div role="group" aria-label="Filter by fit" className="flex flex-wrap gap-2">
        <FitButton active={fit === null} onClick={() => setFilter("fit", null)}>
          All{allCount !== null && ` ${allCount}`}
        </FitButton>
        {FITS.map((f) => (
          <FitButton key={f} active={fit === f} onClick={() => setFilter("fit", f)}>
            {fitLabel[f]}
            {counts && ` ${counts[f] ?? 0}`}
          </FitButton>
        ))}
      </div>

      {list.isPending && <Loading label="Loading opportunities…" />}
      {list.error && <ErrorState error={list.error} onRetry={() => void list.refetch()} />}
      {list.data && (
        <Results items={list.data.items} filtered={fit !== null || decision !== null} />
      )}
    </>
  );
}

function FitButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={`min-h-11 cursor-pointer rounded-full border px-4 text-sm font-semibold ${
        active ? "border-sea bg-sea text-white" : "border-line bg-white text-ink"
      }`}
    >
      {children}
    </button>
  );
}

function Results({ items, filtered }: { items: Item[]; filtered: boolean }) {
  if (items.length === 0) {
    return filtered ? (
      <Empty title="Nothing matches these filters" />
    ) : (
      <Empty title="No matches yet">
        Matches appear here as your company facts are checked against each call.
      </Empty>
    );
  }
  // Spec: goal-relevant opportunities first, the others under "Other matches". The API
  // already orders them; the heading only appears when both groups exist.
  const relevant = items.filter((i) => i.goal_relevant);
  const others = items.filter((i) => !i.goal_relevant);
  return (
    <>
      {relevant.length > 0 && <ItemList items={relevant} label="Matched opportunities" />}
      {others.length > 0 &&
        (relevant.length > 0 ? (
          <section aria-labelledby="other-matches" className="flex flex-col gap-3">
            <h2 id="other-matches" className="m-0 text-base font-semibold">
              Other matches
            </h2>
            <ItemList items={others} label="Other matches" />
          </section>
        ) : (
          <ItemList items={others} label="Matched opportunities" />
        ))}
    </>
  );
}

function ItemList({ items, label }: { items: Item[]; label: string }) {
  return (
    <ul aria-label={label} className="m-0 flex list-none flex-col gap-3 p-0">
      {items.map((item) => (
        <li key={item.id}>
          <ItemRow item={item} />
        </li>
      ))}
    </ul>
  );
}

export function ItemRow({ item }: { item: Item }) {
  const upcoming = item.status === "upcoming";
  const when = upcoming
    ? openingLabel(item.opening, item.expected_month)
    : deadlineLabel(item.deadline);
  const soon = !upcoming && item.deadline.kind === "days_left";
  const decision = decisionLabel[item.decision];
  return (
    <Link
      to={`/opportunities/${item.id}`}
      className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-card bg-white p-5 text-ink no-underline shadow-card"
    >
      <span className="flex min-w-0 flex-[1_1_280px] flex-col gap-1">
        <span className="font-semibold">{item.name}</span>
        <span className="text-sm text-ink-muted">
          {[
            typesLabel(item.types),
            scopeLabel[item.scope],
            checkedLabel(item.checked_days_ago),
          ].join(" · ")}
        </span>
        {(item.readiness || item.based_on_last_edition) && (
          <span className="text-xs text-ink-muted">
            {[
              item.readiness && readinessLabel(item.readiness),
              item.based_on_last_edition && "based on last edition",
            ]
              .filter(Boolean)
              .join(" · ")}
          </span>
        )}
      </span>
      <span className="flex flex-wrap items-center gap-2">
        {item.recheck_due && <Pill tone="unknown">Re-check due</Pill>}
        {decision && <Pill tone="unknown">{decision}</Pill>}
        <Pill tone={fitTone[item.fit.status]}>
          {fitLabel[item.fit.status]}
          {item.fit.few_explicit_rules && " · few explicit rules"}
        </Pill>
        {when &&
          (soon ? (
            <Pill tone="deadline">{when}</Pill>
          ) : (
            <span className="text-sm text-ink-muted">{when}</span>
          ))}
      </span>
    </Link>
  );
}
