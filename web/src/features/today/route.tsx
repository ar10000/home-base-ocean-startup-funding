import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import type { components } from "../../api/schema";
import { Card, ErrorState, Loading } from "../../components/States";
import { api, unwrap } from "../../lib/api";
import { factLabel, goalLabel, windowLabel } from "../../lib/format";
import { useMe } from "../account/AuthGate";
import { formatDate, minutesLabel, readinessLabel, taskSentence, type Task } from "./wording";

type Today = components["schemas"]["Today"];

export const todayKey = ["today"] as const;

export function useToday() {
  return useQuery({ queryKey: todayKey, queryFn: async () => unwrap(await api.GET("/today")) });
}

// Morning, afternoon or evening by Lisbon time (spec: "Greeting and name"; evening, D-66).
function greeting(now: Date): string {
  const hour = Number(
    new Intl.DateTimeFormat("en-GB", {
      hour: "numeric",
      hourCycle: "h23",
      timeZone: "Europe/Lisbon",
    }).format(now),
  );
  if (hour < 12) return "Good morning";
  return hour < 18 ? "Good afternoon" : "Good evening";
}

const eyebrowFormat = new Intl.DateTimeFormat("en-GB", {
  weekday: "long",
  day: "numeric",
  month: "long",
  timeZone: "Europe/Lisbon",
});

/** Where a task is done: its opportunity, or the profile for facts and goals (D-67). */
function taskLink(task: Task): string | null {
  if (task.opportunity_id) return `/opportunities/${task.opportunity_id}`;
  if (task.type === "check_goals") return "/profile#goals";
  if (task.type === "add_fact") return "/profile#facts";
  return null;
}

export function Component() {
  const today = useToday();
  const me = useMe();
  const name = me.data?.given_name;
  const now = new Date();

  return (
    <>
      <header>
        <div className="text-xs font-semibold tracking-[0.08em] text-ink-muted uppercase">
          {eyebrowFormat.format(now)}
        </div>
        <h1 className="mt-1.5 text-4xl font-semibold tracking-tight">
          {name ? `${greeting(now)}, ${name}` : greeting(now)}
        </h1>
      </header>
      {today.data && <StageCard stage={today.data.stage} />}
      {today.isPending && <Loading label="Loading today…" />}
      {today.error && <ErrorState error={today.error} onRetry={() => void today.refetch()} />}
      {today.data && <TodayBody today={today.data} />}
    </>
  );
}

export function TodayBody({ today }: { today: Today }) {
  return (
    <>
      {today.current_goal && today.current_goal.length > 0 && (
        <Card>
          <h2 className="eyebrow">Working towards</h2>
          <ul className="m-0 mt-2 flex list-none flex-col gap-1 p-0 text-sm">
            {today.current_goal.map((g) => (
              <li key={g.goal} className="flex justify-between gap-3">
                <span className="font-semibold">{goalLabel[g.goal] ?? g.goal}</span>
                <span className="text-ink-muted">{windowLabel[g.window] ?? g.window}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <div className="flex flex-wrap gap-5">
        <OneThing
          task={today.one_thing}
          nextOpening={today.mode === "preparing" ? today.next_opening : null}
        />
        {today.mode === "applying" && today.next_deadline && (
          <NextDeadline d={today.next_deadline} />
        )}
        {today.mode === "preparing" && today.top_fact && <TopFact f={today.top_fact} />}
      </div>

      {today.needs_attention.length > 0 && (
        <Card>
          <h2 className="m-0 text-base font-semibold">Needs your attention</h2>
          <ul className="m-0 mt-2 list-none p-0">
            {today.needs_attention.map((task, i) => (
              <li
                key={`${task.type}-${task.opportunity_id ?? ""}-${i}`}
                className="border-t border-divider"
              >
                <TaskRow task={task} />
              </li>
            ))}
          </ul>
        </Card>
      )}

      {today.mode === "preparing" && today.opening_soon.length > 0 && (
        <Card>
          <h2 className="m-0 text-base font-semibold">Opening soon</h2>
          <ul className="m-0 mt-2 list-none p-0">
            {today.opening_soon.map((o) => (
              <li
                key={o.opportunity_id}
                className="flex flex-wrap items-center gap-4 border-t border-divider py-4"
              >
                <Link
                  to={`/opportunities/${o.opportunity_id}`}
                  className="flex-[1_1_260px] text-ink no-underline"
                >
                  <span className="block font-semibold">{o.opportunity}</span>
                  <span className="mt-0.5 block text-sm text-ink-muted">
                    Opens {formatDate(o.opening)}
                  </span>
                </Link>
                {o.readiness && (
                  <span className="text-xs text-ink-muted">{readinessLabel(o.readiness)}</span>
                )}
              </li>
            ))}
          </ul>
        </Card>
      )}
    </>
  );
}

function TaskRow({ task }: { task: Task }) {
  const row = "flex min-h-14 items-center justify-between gap-3 text-ink no-underline";
  const body = (
    <>
      <span>{taskSentence(task)}</span>
      <span className="text-xs text-ink-muted">{minutesLabel(task.minutes)}</span>
    </>
  );
  const to = taskLink(task);
  return to ? (
    <Link to={to} className={row}>
      {body}
    </Link>
  ) : (
    <div className={row}>{body}</div>
  );
}

function OneThing({
  task,
  nextOpening,
}: {
  task: Task | null;
  nextOpening: string | null | undefined;
}) {
  return (
    <Card className="flex flex-[3_1_380px] flex-col gap-3 !rounded-hero">
      <div className="eyebrow flex items-center gap-2">
        <span>Your one thing today</span>
      </div>
      {task ? (
        <>
          <h2 className="m-0 text-2xl leading-tight font-bold">{taskSentence(task)}</h2>
          <p className="m-0 text-sm text-ink-muted">{minutesLabel(task.minutes)}</p>
          {taskLink(task) && (
            <Link to={taskLink(task) ?? "/"} className="btn-primary self-start">
              Open
            </Link>
          )}
        </>
      ) : (
        <>
          <h2 className="m-0 text-2xl leading-tight font-bold">You're all set</h2>
          {nextOpening && (
            <p className="m-0 text-sm text-ink-muted">
              The next call opens {formatDate(nextOpening)}.
            </p>
          )}
        </>
      )}
    </Card>
  );
}

function NextDeadline({ d }: { d: NonNullable<Today["next_deadline"]> }) {
  const share =
    d.answers_ready && d.answers_ready.total > 0
      ? d.answers_ready.ready / d.answers_ready.total
      : null;
  return (
    <Link
      to={`/opportunities/${d.opportunity_id}`}
      className="flex flex-[2_1_260px] flex-col gap-2.5 rounded-hero bg-white p-6 text-ink no-underline shadow-card"
    >
      <span className="eyebrow">Next deadline</span>
      <span className="flex items-baseline gap-2.5">
        <span className="text-6xl leading-none font-light tracking-tight text-sea">
          {d.days_left}
        </span>
        <span className="text-sm text-ink-muted">{d.days_left === 1 ? "day" : "days"}</span>
      </span>
      <span className="font-semibold">
        {d.opportunity} · {formatDate(d.deadline)}
      </span>
      {d.answers_ready && share !== null && (
        <>
          <span
            aria-hidden="true"
            className="mt-auto block h-2 overflow-hidden rounded-full bg-mist"
          >
            <span
              className="block h-2 rounded-full bg-sea"
              style={{ width: `${Math.round(share * 100)}%` }}
            />
          </span>
          <span className="text-sm text-ink-muted">
            {d.answers_ready.ready} of {d.answers_ready.total} answers ready
          </span>
        </>
      )}
    </Link>
  );
}

function TopFact({ f }: { f: NonNullable<Today["top_fact"]> }) {
  return (
    <Card className="flex flex-[2_1_260px] flex-col gap-2.5 !rounded-hero">
      <span className="eyebrow">The fact that unlocks the most</span>
      <span className="font-semibold">{capitalised(factLabel(f.fact))}</span>
      <span className="text-sm text-ink-muted">
        Adding {factLabel(f.fact)} settles {f.matches} {f.matches === 1 ? "match" : "matches"} and
        unlocks {f.questions} {f.questions === 1 ? "answer" : "answers"}
      </span>
    </Card>
  );
}

/** Spec: Today > Stage (D-78), as in the wireframe: done stages sea green, the current one
coral (the palette keeps coral for "your current stage"), the rest sea mist. */
export function StageCard({ stage }: { stage: Today["stage"] }) {
  if (!stage) {
    return (
      <Link to="/profile#stage" className="self-start text-sm font-semibold">
        Choose your stage
      </Link>
    );
  }
  return (
    <Link
      to="/profile#stage"
      className="flex max-w-sm flex-col gap-2.5 self-start rounded-[18px] bg-white px-4.5 py-3.5 text-ink no-underline shadow-card"
    >
      <span className="flex justify-between gap-3 text-sm">
        <span className="font-semibold">
          Stage {stage.position} of {stage.total}
        </span>
        <span className="text-ink-muted">{stage.label}</span>
      </span>
      <span aria-hidden="true" className="flex gap-1">
        {Array.from({ length: stage.total }, (_, i) => (
          <span
            key={i}
            className={`h-2 flex-1 rounded-full ${
              i + 1 < stage.position ? "bg-sea" : i + 1 === stage.position ? "bg-coral" : "bg-mist"
            }`}
          />
        ))}
      </span>
    </Link>
  );
}

function capitalised(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}
