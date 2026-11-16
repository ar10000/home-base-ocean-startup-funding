import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { components } from "../src/api/schema";
import { AUTOSAVE_MS } from "../src/features/applications/detail-route";
import { fakeApi, onboardedMe, problem } from "./fake-api";
import { renderAt } from "./render";

type Application = components["schemas"]["ApplicationOut"];
type Question = components["schemas"]["QuestionOut"];
const ID = "app-1";

const question = (over: Partial<Question>): Question => ({
  id: "q1",
  position: 1,
  text: "Describe the environmental benefit",
  state: "missing_facts",
  answer: null,
  draftable: false,
  missing: [],
  required_facts: [],
  built_from: [],
  ...over,
});

const app = (over: Partial<Application> = {}): Application => ({
  id: ID,
  opportunity: "Blue Bio Value",
  opportunity_id: "opp-1",
  status: "in_progress",
  deadline: { kind: "days_left", date: "2026-11-21", days_left: 12 },
  answers_ready: { ready: 1, total: 2 },
  questions_known: true,
  no_longer_eligible: false,
  call_removed: false,
  started_at: "2026-11-10T10:00:00+00:00",
  submitted_at: null,
  questions: [
    question({
      id: "q1",
      position: 1,
      state: "approved",
      answer: "We farm seaweed.",
      built_from: ["f1", "f2"],
    }),
    question({
      id: "q2",
      position: 2,
      text: "Team",
      state: "missing_facts",
      missing: ["team_size"],
    }),
  ],
  ...over,
});

/** A small in-memory API for one application. */
function serve(initial: Application, overrides: Record<string, (r: Request) => unknown> = {}) {
  let current = initial;
  const writes: { path: string; body: unknown }[] = [];
  const setAnswer = (qid: string, patch: Partial<Question>) => {
    current = {
      ...current,
      questions: current.questions.map((q) => (q.id === qid ? { ...q, ...patch } : q)),
    };
  };
  fakeApi({
    "GET /me": () => onboardedMe,
    "GET /applications": () => [
      {
        id: ID,
        opportunity: current.opportunity,
        opportunity_id: current.opportunity_id,
        status: current.status,
        answers_ready: current.answers_ready,
        call_removed: current.call_removed,
      },
    ],
    [`GET /applications/${ID}`]: () => current,
    [`PUT /applications/${ID}/answers/q2`]: async (r) => {
      const body = (await r.json()) as { text: string };
      writes.push({ path: "PUT q2", body });
      setAnswer("q2", { answer: body.text, state: "edited" });
      return current;
    },
    [`POST /applications/${ID}/answers/q2/approve`]: () => {
      writes.push({ path: "approve q2", body: null });
      setAnswer("q2", { state: "approved" });
      current = { ...current, status: "ready", answers_ready: { ready: 2, total: 2 } };
      return current;
    },
    [`POST /applications/${ID}/submitted`]: () => {
      writes.push({ path: "submitted", body: null });
      current = { ...current, status: "submitted", submitted_at: "2026-11-15T10:00:00+00:00" };
      return current;
    },
    ...overrides,
  });
  return writes;
}

describe("Applications list", () => {
  it("says how to start when there are none", async () => {
    fakeApi({ "GET /me": () => onboardedMe, "GET /applications": () => [] });
    renderAt("/applications");
    expect(await screen.findByText("No applications yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "opportunity" })).toHaveAttribute(
      "href",
      "/opportunities",
    );
  });

  it("lists each application with its status and answers ready", async () => {
    serve(app());
    renderAt("/applications");
    const link = await screen.findByRole("link", { name: /Blue Bio Value/ });
    expect(link).toHaveAttribute("href", `/applications/${ID}`);
    expect(within(link).getByText("1 of 2 answers ready")).toBeInTheDocument();
    expect(within(link).getByText("In progress")).toBeInTheDocument();
  });

  it("shows the API's problem", async () => {
    fakeApi({
      "GET /me": () => onboardedMe,
      "GET /applications": () => problem(500, "Error", "list broke"),
    });
    renderAt("/applications");
    expect(await screen.findByRole("alert")).toHaveTextContent("list broke");
  });
});

describe("Application workspace", () => {
  it("shows progress, days left, status and each question's state", async () => {
    serve(app());
    renderAt(`/applications/${ID}`);
    expect(
      await screen.findByRole("heading", { level: 1, name: "Blue Bio Value" }),
    ).toBeInTheDocument();
    expect(screen.getByText("1 of 2 ready")).toBeInTheDocument();
    expect(screen.getByText("12 days left")).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Questions" });
    expect(
      within(nav)
        .getAllByRole("button")
        .map((b) => b.textContent),
    ).toEqual(["1. Describe the environmental benefitApproved", "2. TeamMissing facts"]);
    expect(screen.getByText("Built from 2 approved facts")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approved" })).toBeDisabled();
    expect(screen.getByText("Nothing is submitted from here.")).toBeInTheDocument();
  });

  it("says when the call's questions are not known yet", async () => {
    serve(app({ questions_known: false, questions: [], answers_ready: null }));
    renderAt(`/applications/${ID}`);
    expect(await screen.findByText("The call's questions are not known yet")).toBeInTheDocument();
  });

  it("names the missing facts, autosaves after a pause, then approves", async () => {
    const writes = serve(app());
    renderAt(`/applications/${ID}`);
    fireEvent.click(await screen.findByRole("button", { name: /2\. Team/ }));
    expect(screen.getByText("team size")).toBeInTheDocument();
    const approve = screen.getByRole("button", { name: "Approve" });
    expect(approve).toBeDisabled(); // nothing written yet
    const box = screen.getByLabelText("Team");
    fireEvent.change(box, { target: { value: "Two" } });
    fireEvent.change(box, { target: { value: "Two founders" } });
    expect(writes).toEqual([]);
    expect(approve).toBeDisabled(); // not saved yet
    await waitFor(
      () => expect(screen.getByRole("status", { name: "" })).toHaveTextContent("Saved"),
      {
        timeout: AUTOSAVE_MS + 1500,
      },
    );
    expect(writes).toEqual([{ path: "PUT q2", body: { text: "Two founders" } }]);
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    expect(await screen.findByText("2 of 2 ready")).toBeInTheDocument();
    expect(writes.at(-1)).toEqual({ path: "approve q2", body: null });
  });

  it("does not offer to approve a blank answer", async () => {
    const writes = serve(app());
    renderAt(`/applications/${ID}`);
    fireEvent.click(await screen.findByRole("button", { name: /2\. Team/ }));
    fireEvent.change(screen.getByLabelText("Team"), { target: { value: "   " } });
    await waitFor(() => expect(writes).toHaveLength(1), { timeout: AUTOSAVE_MS + 1500 });
    expect(screen.getByRole("button", { name: "Approve" })).toBeDisabled();
  });

  it("saves unsaved text when the founder switches question", async () => {
    const writes = serve(app());
    renderAt(`/applications/${ID}`);
    fireEvent.click(await screen.findByRole("button", { name: /2\. Team/ }));
    fireEvent.change(screen.getByLabelText("Team"), { target: { value: "Two founders" } });
    fireEvent.click(screen.getByRole("button", { name: /1\. Describe/ }));
    await waitFor(() =>
      expect(writes).toEqual([{ path: "PUT q2", body: { text: "Two founders" } }]),
    );
  });

  it("marks as submitted only after the founder confirms", async () => {
    const writes = serve(app({ status: "ready" }));
    renderAt(`/applications/${ID}`);
    fireEvent.click(await screen.findByRole("button", { name: "Mark as submitted" }));
    fireEvent.click(screen.getByRole("button", { name: "Not yet" }));
    expect(writes).toEqual([]);
    fireEvent.click(screen.getByRole("button", { name: "Mark as submitted" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, mark as submitted" }));
    expect(
      await screen.findByText("You marked this application as submitted."),
    ).toBeInTheDocument();
    expect(writes).toEqual([{ path: "submitted", body: null }]);
  });

  it("offers to archive an application that is no longer eligible, then goes to the list", async () => {
    let archived = false;
    serve(app({ no_longer_eligible: true }), {
      [`POST /applications/${ID}/archive-not-eligible`]: () => {
        archived = true;
        return new Response(null, { status: 204 });
      },
    });
    const router = renderAt(`/applications/${ID}`);
    expect(await screen.findByText("No longer eligible.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Archive it" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/applications"));
    expect(archived).toBe(true);
  });

  it("keeps an application whose call was removed read only (D-73)", async () => {
    const writes = serve(app({ call_removed: true, no_longer_eligible: true }));
    renderAt(`/applications/${ID}`);
    expect(await screen.findByText("This call is no longer listed.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /2\. Team/ }));
    const box = screen.getByLabelText("Team");
    expect(box).toHaveAttribute("readonly");
    fireEvent.change(box, { target: { value: "edited" } });
    expect(screen.queryByRole("button", { name: /^Approved?$/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mark as submitted" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Archive it" })).not.toBeInTheDocument();
    await new Promise((r) => setTimeout(r, AUTOSAVE_MS + 300));
    expect(writes).toEqual([]);
  });

  it("marks a removed call in the list", async () => {
    serve(app({ call_removed: true }));
    renderAt("/applications");
    expect(await screen.findByText("No longer listed · read only")).toBeInTheDocument();
  });

  it("shows why a save was refused", async () => {
    serve(app(), {
      [`PUT /applications/${ID}/answers/q2`]: () => problem(409, "Conflict", "already submitted"),
    });
    renderAt(`/applications/${ID}`);
    fireEvent.click(await screen.findByRole("button", { name: /2\. Team/ }));
    fireEvent.change(screen.getByLabelText("Team"), { target: { value: "x" } });
    expect(await screen.findByRole("alert", {}, { timeout: AUTOSAVE_MS + 1500 })).toHaveTextContent(
      "already submitted",
    );
  });
});
