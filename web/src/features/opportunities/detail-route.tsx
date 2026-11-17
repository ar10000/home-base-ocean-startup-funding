import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router";
import type { components } from "../../api/schema";
import { Pill } from "../../components/Pill";
import { Card, ErrorState, Loading } from "../../components/States";
import { api, unwrap } from "../../lib/api";
import {
  checkedLabel,
  deadlineLabel,
  decisionLabel,
  FOUNDER_FACT_FOR,
  factLabel,
  fitLabel,
  formatDate,
  openingLabel,
  readinessLabel,
  scopeLabel,
  typesLabel,
} from "../../lib/format";
import { fitTone } from "./list-route";
import { historySentence, reasonLabel } from "./history";

type Detail = components["schemas"]["OpportunityDetail"];
type Decision = components["schemas"]["Decision"];
type Reason = components["schemas"]["NotForUsReason"];
type Requirement = components["schemas"]["RequirementLine"];

const DECISIONS: Exclude<Decision, "none">[] = ["pursuing", "later", "not_for_us"];

/** Spec, Upcoming opportunities: what an expected month is based on. */
const evidenceLabel: Record<string, string> = {
  previous_edition: "the previous edition",
  announcement: "an organiser announcement",
};

export function useOpportunity(id: string) {
  return useQuery({
    queryKey: ["opportunity", id],
    queryFn: async () =>
      unwrap(
        await api.GET("/opportunities/{opportunity_id}", {
          params: { path: { opportunity_id: id } },
        }),
      ),
  });
}

export function Component() {
  const { id = "" } = useParams();
  const detail = useOpportunity(id);
  return (
    <>
      <Link to="/opportunities" className="text-sm font-semibold no-underline">
        ← Opportunities
      </Link>
      {detail.isPending && <Loading label="Loading the opportunity…" />}
      {detail.error && <ErrorState error={detail.error} onRetry={() => void detail.refetch()} />}
      {detail.data && <OpportunityBody o={detail.data} />}
    </>
  );
}

export function OpportunityBody({ o }: { o: Detail }) {
  const upcoming = o.status === "upcoming";
  const when = upcoming ? openingLabel(o.opening, o.expected_month) : deadlineLabel(o.deadline);
  return (
    <>
      <header className="flex flex-wrap items-start justify-between gap-5">
        <div className="flex min-w-0 flex-col gap-2">
          <h1 className="m-0 text-4xl font-semibold tracking-tight">{o.name}</h1>
          <p className="m-0 text-sm text-ink-muted">
            {[o.funder, typesLabel(o.types), scopeLabel[o.scope]].join(" · ")}
          </p>
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <Pill tone={fitTone[o.fit.status]}>
              {fitLabel[o.fit.status]}
              {o.fit.few_explicit_rules && " · few explicit rules"}
            </Pill>
            {when &&
              (!upcoming && o.deadline.kind === "days_left" ? (
                <Pill tone="deadline">
                  Closes {o.deadline.date && formatDate(o.deadline.date)} · {when}
                </Pill>
              ) : (
                <span className="text-ink-muted">{upcoming ? when : `Closes ${when}`}</span>
              ))}
            {o.recheck_due && <Pill tone="unknown">Re-check due</Pill>}
            <span className="text-ink-muted">
              Source {checkedLabel(o.checked_days_ago).toLowerCase()} ·{" "}
              <a href={o.source_url} target="_blank" rel="noreferrer">
                official call
              </a>
            </span>
          </div>
        </div>
        <StartApplication id={o.id} />
      </header>

      <Decisions id={o.id} current={o.decision} />

      {upcoming && o.expected_month && o.evidence.length > 0 && (
        <Card>
          <h2 className="eyebrow">Expected opening</h2>
          <ul className="m-0 mt-2 list-none p-0 text-sm">
            {o.evidence.map((e) => (
              <li key={e.url}>
                Based on{" "}
                <a href={e.url} target="_blank" rel="noreferrer">
                  {evidenceLabel[e.kind] ?? e.kind}
                </a>{" "}
                ({formatDate(e.dated)})
              </li>
            ))}
          </ul>
        </Card>
      )}

      {o.requirements.length > 0 && <WhyItFits o={o} />}

      <Card>
        <h2 className="m-0 text-base font-semibold">Eligibility, checked against your facts</h2>
        {o.based_on_last_edition && (
          <p className="m-0 mt-1 text-xs text-ink-muted">based on last edition</p>
        )}
        {o.requirements.length === 0 ? (
          <p className="m-0 mt-3 text-sm text-ink-muted">
            The call lists no requirements we could check.
          </p>
        ) : (
          <ul className="m-0 mt-3 flex list-none flex-col p-0">
            {o.requirements.map((r, i) => (
              <RequirementRow key={i} r={r} />
            ))}
          </ul>
        )}
      </Card>

      {o.questions_total !== null && o.questions_total > 0 && (
        <p className="m-0 text-sm text-ink-muted">
          The application has {o.questions_total}{" "}
          {o.questions_total === 1 ? "question" : "questions"}; {o.questions_draftable} can be
          drafted from your facts.
          {o.readiness && ` ${readinessLabel(o.readiness)}.`}
        </p>
      )}

      <Card>
        <h2 className="eyebrow">History</h2>
        {o.history.length === 0 ? (
          <p className="m-0 mt-2 text-sm text-ink-muted">Nothing has happened here yet.</p>
        ) : (
          <ol className="m-0 mt-2 flex list-none flex-col p-0">
            {o.history.map((h, i) => (
              <li
                key={i}
                className="flex gap-4 border-t border-divider py-2.5 text-sm first:border-t-0"
              >
                <span className="w-16 shrink-0 text-ink-muted">
                  {formatDate(h.occurred_at.slice(0, 10))}
                </span>
                <span>{historySentence(h)}</span>
              </li>
            ))}
          </ol>
        )}
      </Card>
    </>
  );
}

const resultMark: Record<
  Requirement["result"],
  { mark: string; label: string; className: string }
> = {
  pass: { mark: "✓", label: "Meets", className: "bg-mist text-sea-deep" },
  fail: { mark: "✕", label: "Does not meet", className: "bg-unknown text-ink" },
  unknown: { mark: "?", label: "Unknown", className: "bg-unknown text-unknown-ink" },
  ai_judgement: { mark: "?", label: "AI judgement", className: "bg-coral-soft text-ink" },
};

function RequirementRow({ r }: { r: Requirement }) {
  const m = resultMark[r.result];
  return (
    <li className="flex gap-3 border-t border-divider py-3 first:border-t-0">
      <span
        role="img"
        aria-label={m.label}
        className={`flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-bold ${m.className}`}
      >
        {m.mark}
      </span>
      <span className="flex min-w-0 flex-col gap-1">
        <span className="font-semibold">
          {r.criterion ?? r.quote}
          {r.result === "ai_judgement" && (
            <span className="ml-2 align-middle">
              <Pill tone="ai">AI judgement</Pill>
            </span>
          )}
          {r.result === "unknown" && r.fact && (
            <Link
              to={r.fact in FOUNDER_FACT_FOR ? "/profile#founders" : "/profile#facts"}
              className="ml-2 text-sm font-normal"
            >
              {r.fact in FOUNDER_FACT_FOR
                ? `add the ${factLabel(r.fact)} (optional, private)`
                : `needs your ${factLabel(r.fact)}`}
            </Link>
          )}
        </span>
        {r.criterion && <q className="text-sm text-ink-muted">{r.quote}</q>}
      </span>
    </li>
  );
}

function Decisions({ id, current }: { id: string; current: Decision }) {
  const queryClient = useQueryClient();
  const change = useMutation({
    mutationFn: async (body: { decision: Decision; reason?: Reason | null }) =>
      unwrap(
        await api.PUT("/opportunities/{opportunity_id}/decision", {
          params: { path: { opportunity_id: id } },
          body,
        }),
      ),
    onSuccess: async () => {
      // A decision moves the opportunity between lists: drop them rather than show a
      // stale list while it refetches.
      queryClient.removeQueries({ queryKey: ["opportunities"] });
      await queryClient.invalidateQueries();
    },
  });
  return (
    <section aria-labelledby="decision" className="flex flex-col gap-3">
      <h2 id="decision" className="eyebrow">
        Your decision
      </h2>
      <div role="group" aria-labelledby="decision" className="flex flex-wrap items-center gap-2">
        {DECISIONS.map((d) => (
          <button
            key={d}
            type="button"
            aria-pressed={current === d}
            disabled={change.isPending}
            onClick={() => change.mutate({ decision: d })}
            className={current === d ? "btn-primary" : "btn-secondary"}
          >
            {decisionLabel[d]}
          </button>
        ))}
        {current === "not_for_us" && (
          <label className="flex items-center gap-2 text-sm text-ink-muted">
            Reason (optional)
            <select
              defaultValue=""
              disabled={change.isPending}
              onChange={(e) =>
                e.target.value &&
                change.mutate({ decision: "not_for_us", reason: e.target.value as Reason })
              }
              className="min-h-11 rounded-full border border-line bg-white px-3 text-ink"
            >
              <option value="">—</option>
              {(Object.keys(reasonLabel) as Reason[]).map((r) => (
                <option key={r} value={r}>
                  {reasonLabel[r]}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      {change.error && <ErrorState error={change.error} />}
    </section>
  );
}

function StartApplication({ id }: { id: string }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  // One application per call: once started, the button opens it. If the list can't be
  // read, starting is still offered; the API returns the existing application anyway.
  const applications = useQuery({
    queryKey: ["applications"],
    queryFn: async () => unwrap(await api.GET("/applications")),
  });
  const existing = applications.data?.find((a) => a.opportunity_id === id);
  const start = useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST("/opportunities/{opportunity_id}/application", {
          params: { path: { opportunity_id: id } },
        }),
      ),
    onSuccess: async ({ application_id }) => {
      await queryClient.invalidateQueries();
      await navigate(`/applications/${application_id}`);
    },
  });
  if (existing) {
    return (
      <Link to={`/applications/${existing.id}`} className="btn-primary no-underline">
        Open application
      </Link>
    );
  }
  return (
    <div className="flex flex-col items-end gap-2">
      <button
        type="button"
        className="btn-primary"
        disabled={start.isPending}
        onClick={() => start.mutate()}
      >
        {start.isPending ? "Starting…" : "Start application"}
      </button>
      {start.error && <ErrorState error={start.error} />}
    </div>
  );
}

/** D-82: the calculated fit in words, marked as AI. It explains; it never sets the fit. */
function WhyItFits({ o }: { o: Detail }) {
  const results = o.requirements.map((r) => r.result).join(",");
  const why = useQuery({
    // Same fit and results: same words (the API caches by input too).
    queryKey: ["why-it-fits", o.id, o.fit.status, results],
    queryFn: async () =>
      unwrap(
        await api.POST("/opportunities/{opportunity_id}/why-it-fits", {
          params: { path: { opportunity_id: o.id } },
        }),
      ),
    retry: false,
    staleTime: Infinity,
  });
  if (why.isError) return null; // the fit and requirements below say it all without words
  return (
    <Card className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <h2 className="m-0 text-base font-semibold">Why it fits</h2>
        <Pill tone="ai">AI</Pill>
      </div>
      <p className="m-0 text-sm" aria-live="polite">
        {why.isPending ? (
          <span className="text-ink-muted">Putting it into words…</span>
        ) : (
          why.data.text
        )}
      </p>
    </Card>
  );
}
