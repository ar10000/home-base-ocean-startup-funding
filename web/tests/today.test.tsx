import { screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { components } from "../src/api/schema";
import { formatDate, taskSentence, type Task } from "../src/features/today/wording";
import { fakeApi, onboardedMe, problem } from "./fake-api";
import { renderAt } from "./render";

type Today = components["schemas"]["Today"];

const empty: Today = {
  stage: null,
  mode: "preparing",
  one_thing: null,
  needs_attention: [],
  next_deadline: null,
  next_opening: null,
  opening_soon: [],
  top_fact: null,
  current_goal: null,
};

const task = (over: Partial<Task>): Task => ({
  type: "add_fact",
  minutes: 10,
  opportunity_id: "00000000-0000-7000-8000-00000000000a",
  opportunity: "Blue Bio Value",
  deadline: "2026-11-21",
  fact: "TRL",
  count: null,
  question: null,
  ...over,
});

function showToday(today: Today, me = onboardedMe) {
  fakeApi({ "GET /me": () => me, "GET /today": () => today });
  renderAt("/");
}

describe("Today screen", () => {
  it("shows a loading state", async () => {
    fakeApi({ "GET /me": () => onboardedMe, "GET /today": () => new Promise(() => {}) });
    renderAt("/");
    expect(await screen.findByText("Loading today…")).toHaveAttribute("role", "status");
  });

  it("shows the API's problem with a retry", async () => {
    fakeApi({
      "GET /me": () => onboardedMe,
      "GET /today": () => problem(500, "Server error", "it broke"),
    });
    renderAt("/");
    expect(await screen.findByRole("alert")).toHaveTextContent("it broke");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("with nothing to do, says You're all set and shows no empty sections", async () => {
    showToday(empty);
    expect(await screen.findByRole("heading", { name: "You're all set" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Needs your attention" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Opening soon" })).not.toBeInTheDocument();
    expect(screen.queryByText("Next deadline")).not.toBeInTheDocument();
    expect(screen.queryByText("Working towards")).not.toBeInTheDocument();
  });

  it("in preparing mode, gives the next opening date with You're all set (PRI-17)", async () => {
    showToday({ ...empty, next_opening: "2027-01-12" });
    expect(
      await screen.findByText(`The next call opens ${formatDate("2027-01-12")}.`),
    ).toBeInTheDocument();
  });

  it("greets the founder by first name, and without a name when the token has none", async () => {
    vi.useFakeTimers({ toFake: ["Date"], now: new Date("2026-11-16T09:00:00Z") });
    showToday(empty);
    expect(
      await screen.findByRole("heading", { level: 1, name: "Good morning, Inês" }),
    ).toBeInTheDocument();
    vi.useRealTimers();
  });

  it.each([
    ["2026-11-16T17:59:00Z", "Good afternoon"],
    ["2026-11-16T18:00:00Z", "Good evening"],
    ["2026-11-16T23:59:00Z", "Good evening"],
    ["2026-11-17T00:00:00Z", "Good morning"],
  ])("at %s (Lisbon is UTC in winter) says %s", async (now, greeting) => {
    vi.useFakeTimers({ toFake: ["Date"], now: new Date(now) });
    showToday(empty, { ...onboardedMe, given_name: null });
    expect(await screen.findByRole("heading", { level: 1, name: greeting })).toBeInTheDocument();
    vi.useRealTimers();
  });

  it("says good afternoon from noon Lisbon time", async () => {
    vi.useFakeTimers({ toFake: ["Date"], now: new Date("2026-11-16T12:00:00Z") });
    showToday(empty, { ...onboardedMe, given_name: null });
    expect(
      await screen.findByRole("heading", { level: 1, name: "Good afternoon" }),
    ).toBeInTheDocument();
    vi.useRealTimers();
  });

  it("in applying mode shows the one thing, its time, the next deadline and what needs attention", async () => {
    showToday({
      ...empty,
      mode: "applying",
      one_thing: task({ type: "add_fact", fact: "nutrient figures" }),
      next_deadline: {
        opportunity: "Blue Bio Value",
        opportunity_id: "00000000-0000-7000-8000-00000000000a",
        deadline: "2026-11-21",
        days_left: 12,
        answers_ready: { ready: 5, total: 8 },
      },
      needs_attention: [
        task({ type: "review_drafts", count: 2, minutes: 5 }),
        task({ type: "answer_one_question", opportunity: "BlueInvest" }),
      ],
    });
    expect(
      await screen.findByRole("heading", { name: "Add nutrient figures" }),
    ).toBeInTheDocument();
    expect(screen.getByText("About 10 minutes", { selector: "p" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open" })).toHaveAttribute(
      "href",
      "/opportunities/00000000-0000-7000-8000-00000000000a",
    );
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("5 of 8 answers ready")).toBeInTheDocument();
    const attention = screen
      .getByRole("heading", { name: "Needs your attention" })
      .closest("section");
    expect(attention).not.toBeNull();
    const items = within(attention as HTMLElement).getAllByRole("listitem");
    expect(within(items[0] as HTMLElement).getByRole("link")).toHaveAttribute(
      "href",
      "/opportunities/00000000-0000-7000-8000-00000000000a",
    );
    expect(items.map((li) => li.textContent)).toEqual([
      "Review 2 draft answersAbout 5 minutes",
      "Answer 1 question for BlueInvestAbout 10 minutes",
    ]);
  });

  it("shows 1 day in the singular, and no progress bar for a call with no questions", async () => {
    showToday({
      ...empty,
      mode: "applying",
      next_deadline: {
        opportunity: "X",
        opportunity_id: "00000000-0000-7000-8000-00000000000b",
        deadline: "2026-11-17",
        days_left: 1,
        answers_ready: null,
      },
    });
    expect(await screen.findByText("day")).toBeInTheDocument();
    expect(screen.queryByText(/answers ready/)).not.toBeInTheDocument();
  });

  it("in preparing mode shows opening soon with readiness, the top fact and the goals", async () => {
    showToday({
      ...empty,
      one_thing: task({ type: "check_goals", opportunity: null, opportunity_id: null, minutes: 5 }),
      opening_soon: [
        {
          opportunity: "Ocean accelerator",
          opportunity_id: "00000000-0000-7000-8000-00000000000c",
          opening: "2027-01-12",
          readiness: { ready: 6, total: 8 },
        },
        {
          opportunity: "Port batch",
          opportunity_id: "00000000-0000-7000-8000-00000000000d",
          opening: "2027-02-01",
          readiness: null,
        },
      ],
      top_fact: { fact: "TRL", matches: 1, questions: 4 },
      current_goal: [{ goal: "investment", window: "later" }],
    });
    expect(
      await screen.findByRole("heading", { name: "Check your goals are still right" }),
    ).toBeInTheDocument();
    // Goals are set on the Profile screen (D-67, D-74).
    expect(screen.getByRole("link", { name: "Open" })).toHaveAttribute("href", "/profile#goals");
    expect(screen.getByText("Ready for 6 of 8 questions")).toBeInTheDocument();
    expect(screen.getAllByText(/Ready for/)).toHaveLength(1);
    expect(screen.getByText(`Opens ${formatDate("2027-01-12")}`)).toBeInTheDocument();
    expect(
      screen.getByText("Adding TRL settles 1 match and unlocks 4 answers"),
    ).toBeInTheDocument();
    expect(screen.getByText("Investment")).toBeInTheDocument();
    expect(screen.getByText("later (6 to 12 months)")).toBeInTheDocument();
  });

  it("names the fact that unlocks the most in words, not as its key", async () => {
    showToday({
      ...empty,
      mode: "preparing",
      top_fact: { fact: "team_size", matches: 2, questions: 1 },
    });
    expect(await screen.findByText("Team size")).toBeInTheDocument();
    expect(
      screen.getByText("Adding team size settles 2 matches and unlocks 1 answer"),
    ).toBeInTheDocument();
    expect(screen.queryByText(/team_size/)).not.toBeInTheDocument();
  });

  it("does not show the deadline in preparing mode or opening soon in applying mode", async () => {
    showToday({
      ...empty,
      mode: "applying",
      opening_soon: [
        {
          opportunity: "Hidden",
          opportunity_id: "00000000-0000-7000-8000-00000000000e",
          opening: "2027-01-01",
          readiness: null,
        },
      ],
      top_fact: { fact: "Hidden fact", matches: 2, questions: 0 },
    });
    await screen.findByRole("heading", { name: "You're all set" });
    expect(screen.queryByText("Hidden")).not.toBeInTheDocument();
    expect(screen.queryByText("Hidden fact")).not.toBeInTheDocument();
  });
});

describe("Today modes", () => {
  it("does not show the next deadline in preparing mode", async () => {
    showToday({
      ...empty,
      mode: "preparing",
      next_deadline: {
        opportunity: "Hidden deadline",
        opportunity_id: "00000000-0000-7000-8000-00000000000f",
        deadline: "2026-11-30",
        days_left: 14,
        answers_ready: null,
      },
    });
    await screen.findByRole("heading", { name: "You're all set" });
    expect(screen.queryByText("Next deadline")).not.toBeInTheDocument();
    expect(screen.queryByText(/Hidden deadline/)).not.toBeInTheDocument();
  });
});

describe("task sentences (spec: Your one thing today, Preparing mode)", () => {
  it.each<[Partial<Task>, string]>([
    [{ type: "add_fact", fact: "TRL" }, "Add TRL"],
    [{ type: "add_fact", fact: "team_size" }, "Add team size"],
    [{ type: "add_fact", fact: "woman_ceo" }, "Add woman CEO"],
    [{ type: "review_drafts", count: 3 }, "Review 3 draft answers"],
    [{ type: "answer_one_question" }, "Answer 1 question for Blue Bio Value"],
    [{ type: "start_application" }, "Start your Blue Bio Value application"],
    [
      { type: "decide", deadline: "2027-01-12" },
      `Decide on Blue Bio Value: opens ${formatDate("2027-01-12")}`,
    ],
    [{ type: "decide", deadline: null }, "Decide on Blue Bio Value"],
    [{ type: "back_on_list" }, "Blue Bio Value is back on your list"],
    [{ type: "check_goals" }, "Check your goals are still right"],
    [{ type: "next_answer", question: 3 }, "Work on question 3 of your Blue Bio Value application"],
    [{ type: "next_answer", question: null }, "Work on your Blue Bio Value application"],
  ])("%o → %s", (over, sentence) => {
    expect(taskSentence(task(over))).toBe(sentence);
  });
});

describe("Today: stage (D-78)", () => {
  it("shows Stage n of 9 with its name, linking to the profile", async () => {
    showToday({
      ...empty,
      stage: {
        value: "non_dilutive_funding",
        label: "Non-dilutive funding",
        position: 6,
        total: 9,
      },
    });
    const card = await screen.findByRole("link", { name: /Stage 6 of 9/ });
    expect(card).toHaveTextContent("Non-dilutive funding");
    expect(card).toHaveAttribute("href", "/profile#stage");
  });

  it("asks the founder to choose a stage when there is none", async () => {
    showToday(empty);
    expect(await screen.findByRole("link", { name: "Choose your stage" })).toHaveAttribute(
      "href",
      "/profile#stage",
    );
  });
});
