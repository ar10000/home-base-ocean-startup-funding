import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import type { components } from "../../api/schema";
import { Pill, type Tone } from "../../components/Pill";
import { Card, Empty, ErrorState, Loading } from "../../components/States";
import { api, unwrap } from "../../lib/api";
import { deadlineLabel, factLabel } from "../../lib/format";
import { answerStateLabel, statusLabel } from "./labels";

type Application = components["schemas"]["ApplicationOut"];
type Question = components["schemas"]["QuestionOut"];
type AnswerState = components["schemas"]["AnswerState"];

/** How long typing must pause before the answer is saved (spec: autosaved). */
export const AUTOSAVE_MS = 800;

const stateTone: Record<AnswerState, Tone> = {
  missing_facts: "unknown",
  ai_draft: "ai",
  edited: "unknown",
  approved: "confirmed",
};

const key = (id: string) => ["application", id] as const;

export function Component() {
  const { id = "" } = useParams();
  const application = useQuery({
    queryKey: key(id),
    queryFn: async () =>
      unwrap(
        await api.GET("/applications/{application_id}", {
          params: { path: { application_id: id } },
        }),
      ),
  });
  return (
    <>
      <Link to="/applications" className="text-sm font-semibold no-underline">
        ← Applications
      </Link>
      {application.isPending && <Loading label="Loading the application…" />}
      {application.error && (
        <ErrorState error={application.error} onRetry={() => void application.refetch()} />
      )}
      {application.data && <Workspace a={application.data} />}
    </>
  );
}

export function Workspace({ a }: { a: Application }) {
  const [selected, setSelected] = useState<string | null>(a.questions[0]?.id ?? null);
  const question = a.questions.find((q) => q.id === selected) ?? a.questions[0] ?? null;
  const share =
    a.answers_ready && a.answers_ready.total > 0
      ? a.answers_ready.ready / a.answers_ready.total
      : 0;

  return (
    <>
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="m-0 text-4xl font-semibold tracking-tight">{a.opportunity}</h1>
          <Link to={`/opportunities/${a.opportunity_id}`} className="text-sm">
            The opportunity
          </Link>
        </div>
        <div className="flex flex-wrap items-center gap-4 text-sm">
          {a.answers_ready && (
            <span className="flex items-center gap-2.5">
              <span className="font-semibold">
                {a.answers_ready.ready} of {a.answers_ready.total} ready
              </span>
              <span
                aria-hidden="true"
                className="block h-2 w-28 overflow-hidden rounded-full bg-mist"
              >
                <span
                  className="block h-2 rounded-full bg-sea"
                  style={{ width: `${Math.round(share * 100)}%` }}
                />
              </span>
            </span>
          )}
          <Pill tone={a.deadline.kind === "days_left" ? "deadline" : "unknown"}>
            {deadlineLabel(a.deadline)}
          </Pill>
          <Pill tone={a.status === "ready" || a.status === "submitted" ? "confirmed" : "unknown"}>
            {statusLabel[a.status]}
          </Pill>
        </div>
      </header>

      {a.call_removed && (
        <div role="status" className="rounded-card bg-unknown px-5 py-4 text-sm text-unknown-ink">
          <strong>This call is no longer listed.</strong> Your application is kept as it was, read
          only.
        </div>
      )}
      {a.no_longer_eligible && !a.call_removed && <NoLongerEligible id={a.id} />}

      {!a.questions_known || a.questions.length === 0 ? (
        <Empty title="The call's questions are not known yet">
          They are added when the call is checked by hand.
        </Empty>
      ) : (
        <div className="flex flex-wrap items-start gap-5">
          <nav aria-label="Questions" className="flex flex-[1_1_220px] flex-col gap-1">
            {a.questions.map((q) => (
              <button
                key={q.id}
                type="button"
                aria-current={q.id === question?.id ? "step" : undefined}
                onClick={() => setSelected(q.id)}
                className={`flex min-h-11 cursor-pointer items-center justify-between gap-2 rounded-nav border-0 px-3.5 text-left text-sm ${
                  q.id === question?.id
                    ? "bg-mist font-semibold text-sea-deep"
                    : "bg-transparent text-ink"
                }`}
              >
                <span>
                  {q.position}. {q.text}
                </span>
                <span className="sr-only">{answerStateLabel[q.state]}</span>
                <StateDot state={q.state} />
              </button>
            ))}
          </nav>
          {question && (
            <AnswerEditor
              key={question.id}
              applicationId={a.id}
              q={question}
              readOnly={a.call_removed}
            />
          )}
        </div>
      )}

      {!a.call_removed && <MarkSubmitted a={a} />}
      <p className="m-0 text-xs text-ink-muted">Nothing is submitted from here.</p>
    </>
  );
}

function StateDot({ state }: { state: AnswerState }) {
  const colour = {
    missing_facts: "bg-line",
    ai_draft: "bg-coral",
    edited: "bg-ink-muted",
    approved: "bg-sea",
  }[state];
  return <span aria-hidden="true" className={`size-2.5 shrink-0 rounded-full ${colour}`} />;
}

export function AnswerEditor({
  applicationId,
  q,
  readOnly = false,
}: {
  applicationId: string;
  q: Question;
  readOnly?: boolean;
}) {
  const queryClient = useQueryClient();
  const [text, setText] = useState(q.answer ?? "");
  const [savedText, setSavedText] = useState(q.answer ?? "");
  const pending = useRef<string | null>(null);
  const path = { application_id: applicationId, question_id: q.id };

  const save = useMutation({
    mutationFn: async (value: string) =>
      unwrap(
        await api.PUT("/applications/{application_id}/answers/{question_id}", {
          params: { path },
          body: { text: value },
        }),
      ),
    onSuccess: (data, value) => {
      setSavedText(value);
      queryClient.setQueryData(key(applicationId), data);
    },
  });
  const approve = useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST("/applications/{application_id}/answers/{question_id}/approve", {
          params: { path },
        }),
      ),
    onSuccess: (data) => queryClient.setQueryData(key(applicationId), data),
  });

  const saveText = save.mutate;
  // Autosave: after a pause in typing, and when leaving the question with unsaved text.
  useEffect(() => {
    if (pending.current === null) return;
    const timer = setTimeout(() => {
      if (pending.current !== null) saveText(pending.current);
      pending.current = null;
    }, AUTOSAVE_MS);
    return () => clearTimeout(timer);
  }, [text, saveText]);
  useEffect(
    () => () => {
      if (pending.current !== null) saveText(pending.current);
    },
    [saveText],
  );

  const blank = text.trim() === "";
  const unsaved = text !== savedText || save.isPending;

  return (
    <Card className="flex flex-[3_1_420px] flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="m-0 text-xl font-semibold">Question {q.position}</h2>
        <Pill tone={stateTone[q.state]}>{answerStateLabel[q.state]}</Pill>
      </div>
      <label className="flex flex-col gap-2 text-sm">
        <span>{q.text}</span>
        <textarea
          rows={8}
          value={text}
          readOnly={readOnly}
          onChange={(e) => {
            if (readOnly) return;
            pending.current = e.target.value;
            setText(e.target.value);
          }}
          className={`rounded-xl border bg-white p-3 font-sans text-base text-ink ${
            q.state === "ai_draft" ? "border-coral border-l-4" : "border-line"
          }`}
        />
      </label>
      {q.missing.length > 0 && (
        <p className="m-0 rounded-xl bg-deadline px-3.5 py-2.5 text-sm text-deadline-ink">
          <strong>Missing:</strong> {q.missing.map(factLabel).join(", ")}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-3">
        {!readOnly && (
          <button
            type="button"
            className="btn-primary"
            disabled={blank || unsaved || approve.isPending || q.state === "approved"}
            onClick={() => approve.mutate()}
          >
            {q.state === "approved" ? "Approved" : "Approve"}
          </button>
        )}
        <span role="status" className="text-sm text-ink-muted">
          {save.isPending ? "Saving…" : save.isSuccess ? "Saved" : ""}
        </span>
        {q.built_from.length > 0 && (
          <span className="text-sm text-ink-muted">
            Built from {q.built_from.length} approved {q.built_from.length === 1 ? "fact" : "facts"}
          </span>
        )}
      </div>
      {(save.error ?? approve.error) && <ErrorState error={save.error ?? approve.error} />}
    </Card>
  );
}

function MarkSubmitted({ a }: { a: Application }) {
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState(false);
  const submit = useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST("/applications/{application_id}/submitted", {
          params: { path: { application_id: a.id } },
        }),
      ),
    onSuccess: (data) => {
      queryClient.setQueryData(key(a.id), data);
      void queryClient.invalidateQueries({ queryKey: ["applications"] });
      void queryClient.invalidateQueries({ queryKey: ["today"] });
    },
  });
  if (a.status === "submitted") {
    return <p className="m-0 text-sm text-ink-muted">You marked this application as submitted.</p>;
  }
  return (
    <div className="flex flex-wrap items-center gap-3">
      {confirming ? (
        <>
          <span className="text-sm">Did you submit it on the funder's site?</span>
          <button
            type="button"
            className="btn-primary"
            disabled={submit.isPending}
            onClick={() => submit.mutate()}
          >
            Yes, mark as submitted
          </button>
          <button type="button" className="btn-secondary" onClick={() => setConfirming(false)}>
            Not yet
          </button>
        </>
      ) : (
        <button type="button" className="btn-secondary" onClick={() => setConfirming(true)}>
          Mark as submitted
        </button>
      )}
      {submit.error && <ErrorState error={submit.error} />}
    </div>
  );
}

function NoLongerEligible({ id }: { id: string }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const archive = useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST("/applications/{application_id}/archive-not-eligible", {
          params: { path: { application_id: id } },
        }),
      ),
    onSuccess: async () => {
      await queryClient.invalidateQueries();
      await navigate("/applications");
    },
  });
  return (
    <div
      role="status"
      className="flex flex-wrap items-center gap-3 rounded-card bg-deadline px-5 py-4 text-sm text-deadline-ink"
    >
      <strong>No longer eligible.</strong>
      <span>A change to your facts or the call means this application no longer fits.</span>
      <button
        type="button"
        className="btn-secondary"
        disabled={archive.isPending}
        onClick={() => archive.mutate()}
      >
        Archive it
      </button>
      {archive.error && <ErrorState error={archive.error} />}
    </div>
  );
}
