import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { components } from "../src/api/schema";
import { historySentence } from "../src/features/opportunities/history";
import { formatDate, formatMonth } from "../src/lib/format";
import { fakeApi, onboardedMe, problem } from "./fake-api";
import { renderAt } from "./render";

type Detail = components["schemas"]["OpportunityDetail"];
const ID = "00000000-0000-7000-8000-0000000000a1";

const detail = (over: Partial<Detail> = {}): Detail => ({
  id: ID,
  name: "Blue Bio Value",
  funder: "Fundação Oceano Azul",
  types: ["accelerator"],
  scope: "blue_specific",
  status: "open",
  fit: { status: "possible", few_explicit_rules: false },
  deadline: { kind: "days_left", date: "2026-11-21", days_left: 12 },
  opening: null,
  expected_month: null,
  based_on_last_edition: false,
  readiness: { ready: 5, total: 8 },
  decision: "none",
  goal_relevant: true,
  checked_days_ago: 2,
  checked_on: "2026-11-13",
  recheck_due: false,
  source_url: "https://example.org/call",
  evidence: [],
  questions_total: 8,
  questions_draftable: 5,
  requirements: [
    {
      hard: true,
      quote: "Startups in the blue bioeconomy",
      fact: "sector",
      criterion: "Blue bioeconomy sector",
      result: "pass",
    },
    {
      hard: true,
      quote: "TRL 5 or higher",
      fact: "trl",
      criterion: "TRL 5 or higher",
      result: "unknown",
    },
    {
      hard: false,
      quote: "A clear environmental benefit",
      fact: null,
      criterion: null,
      result: "ai_judgement",
    },
    {
      hard: true,
      quote: "Registered in the EU",
      fact: "country",
      criterion: "Registered in the EU",
      result: "fail",
    },
  ],
  history: [
    {
      action: "match.recalculated",
      occurred_at: "2026-11-15T10:00:00+00:00",
      before: null,
      after: { fit_status: "possible", few_explicit_rules: false },
    },
    {
      action: "opportunity.added",
      occurred_at: "2026-11-06T09:00:00+00:00",
      before: null,
      after: null,
    },
  ],
  ...over,
});

function show(d: Detail | Response, extra: Record<string, (r: Request) => unknown> = {}) {
  const calls = fakeApi({
    "GET /me": () => onboardedMe,
    [`GET /opportunities/${ID}`]: () => d,
    ...extra,
  });
  return { calls, router: renderAt(`/opportunities/${ID}`) };
}

describe("Opportunity screen", () => {
  it("shows the API's problem for an unknown opportunity", async () => {
    show(problem(404, "Not found", "no such opportunity"));
    expect(await screen.findByRole("alert")).toHaveTextContent("no such opportunity");
  });

  it("shows the title, fit, deadline, source check and link", async () => {
    show(detail());
    expect(
      await screen.findByRole("heading", { level: 1, name: "Blue Bio Value" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Possible")).toBeInTheDocument();
    expect(
      screen.getByText(`Closes ${formatDate("2026-11-21")} · 12 days left`),
    ).toBeInTheDocument();
    expect(screen.getByText(/Source checked 2 days ago/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "official call" })).toHaveAttribute(
      "href",
      "https://example.org/call",
    );
  });

  it("lists each requirement with its result, the call's own words, and AI judgement marked as AI", async () => {
    show(detail());
    const list = (
      await screen.findByRole("heading", { name: "Eligibility, checked against your facts" })
    ).parentElement;
    const rows = within(list as HTMLElement).getAllByRole("listitem");
    expect(rows).toHaveLength(4);
    expect(within(rows[0] as HTMLElement).getByRole("img", { name: "Meets" })).toBeInTheDocument();
    expect(
      within(rows[0] as HTMLElement).getByText("Startups in the blue bioeconomy"),
    ).toBeInTheDocument();
    expect(
      within(rows[1] as HTMLElement).getByRole("img", { name: "Unknown" }),
    ).toBeInTheDocument();
    expect(
      within(rows[1] as HTMLElement).getByText("needs your technology readiness level"),
    ).toBeInTheDocument();
    expect(
      within(rows[2] as HTMLElement).getByText("A clear environmental benefit"),
    ).toBeInTheDocument();
    expect(within(rows[2] as HTMLElement).getAllByText("AI judgement")).toHaveLength(1);
    expect(
      within(rows[3] as HTMLElement).getByRole("img", { name: "Does not meet" }),
    ).toBeInTheDocument();
  });

  it("says so when the call lists no checkable requirements, and hides the question line without questions", async () => {
    show(detail({ requirements: [], questions_total: null, readiness: null, history: [] }));
    expect(
      await screen.findByText("The call lists no requirements we could check."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/The application has/)).not.toBeInTheDocument();
    expect(screen.getByText("Nothing has happened here yet.")).toBeInTheDocument();
  });

  it("gives the question count, how many can be drafted, and readiness", async () => {
    show(detail());
    expect(
      await screen.findByText(
        "The application has 8 questions; 5 can be drafted from your facts. Ready for 5 of 8 questions.",
      ),
    ).toBeInTheDocument();
  });

  it("shows the history in the order the API sends it, in words", async () => {
    show(detail());
    const history = (await screen.findByRole("heading", { name: "History" })).parentElement;
    const items = within(history as HTMLElement)
      .getAllByRole("listitem")
      .map((li) => li.textContent);
    expect(items).toEqual([
      `${formatDate("2026-11-15")}Matched to your company: Possible`,
      `${formatDate("2026-11-06")}Added from the official source`,
    ]);
  });

  it("for an upcoming call shows the expected month and what it is based on", async () => {
    show(
      detail({
        status: "upcoming",
        expected_month: "2027-03",
        based_on_last_edition: true,
        evidence: [
          { kind: "previous_edition", dated: "2026-03-02", url: "https://example.org/2026" },
        ],
      }),
    );
    expect(
      await screen.findByText(`Expected around ${formatMonth("2027-03")}`),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "the previous edition" })).toHaveAttribute(
      "href",
      "https://example.org/2026",
    );
    expect(screen.getByText("based on last edition")).toBeInTheDocument();
    expect(screen.queryByText(/Closes/)).not.toBeInTheDocument();
  });
});

describe("decisions (spec: Founder decisions)", () => {
  it("highlights the current decision and changes it", async () => {
    let decision: Detail["decision"] = "later";
    const bodies: unknown[] = [];
    show(detail(), {
      [`GET /opportunities/${ID}`]: () => detail({ decision }),
      [`PUT /opportunities/${ID}/decision`]: async (r) => {
        const body = (await r.json()) as { decision: Detail["decision"] };
        bodies.push(body);
        decision = body.decision;
        return body;
      },
    });
    expect(await screen.findByRole("button", { name: "Later" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: "Pursuing" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    fireEvent.click(screen.getByRole("button", { name: "Pursuing" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Pursuing" })).toHaveAttribute(
        "aria-pressed",
        "true",
      ),
    );
    expect(bodies).toEqual([{ decision: "pursuing" }]);
  });

  it("asks for an optional reason only for Not for us, and sends it", async () => {
    let decision: Detail["decision"] = "none";
    const bodies: unknown[] = [];
    show(detail(), {
      [`GET /opportunities/${ID}`]: () => detail({ decision }),
      [`PUT /opportunities/${ID}/decision`]: async (r) => {
        const body = (await r.json()) as { decision: Detail["decision"] };
        bodies.push(body);
        decision = body.decision;
        return body;
      },
    });
    await screen.findByRole("button", { name: "Not for us" });
    expect(screen.queryByLabelText("Reason (optional)")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Not for us" }));
    const reason = await screen.findByLabelText("Reason (optional)");
    fireEvent.change(reason, { target: { value: "too_early" } });
    await waitFor(() => expect(bodies).toHaveLength(2));
    expect(bodies).toEqual([
      { decision: "not_for_us" },
      { decision: "not_for_us", reason: "too_early" },
    ]);
  });

  it("shows why a decision was refused", async () => {
    show(detail(), {
      [`PUT /opportunities/${ID}/decision`]: () => problem(409, "Conflict", "decision refused"),
    });
    fireEvent.click(await screen.findByRole("button", { name: "Later" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("decision refused");
  });
});

describe("start application", () => {
  it("opens the workspace the API returns", async () => {
    const { router } = show(detail(), {
      [`POST /opportunities/${ID}/application`]: () => ({ application_id: "app-1" }),
      "GET /applications/app-1": () => problem(404, "Not found"),
    });
    fireEvent.click(await screen.findByRole("button", { name: "Start application" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/applications/app-1"));
  });

  it("opens the application already started instead of offering to start one", async () => {
    show(detail(), {
      "GET /applications": () => [
        {
          id: "app-7",
          opportunity_id: ID,
          opportunity: "Blue call",
          status: "in_progress",
          answers_ready: { ready: 1, total: 3 },
          call_removed: false,
        },
      ],
    });
    expect(await screen.findByRole("link", { name: "Open application" })).toHaveAttribute(
      "href",
      "/applications/app-7",
    );
    expect(screen.queryByRole("button", { name: "Start application" })).not.toBeInTheDocument();
  });

  it("still offers to start when the applications cannot be read", async () => {
    show(detail(), { "GET /applications": () => problem(500, "Server error") });
    expect(await screen.findByRole("button", { name: "Start application" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows why it could not start", async () => {
    show(detail(), {
      [`POST /opportunities/${ID}/application`]: () =>
        problem(409, "Conflict", "the call is not open yet"),
    });
    fireEvent.click(await screen.findByRole("button", { name: "Start application" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("the call is not open yet");
  });
});

describe("history sentences", () => {
  const line = (action: string, before: object | null = null, after: object | null = null) => ({
    action,
    occurred_at: "2026-11-15T10:00:00+00:00",
    before: before as Record<string, unknown> | null,
    after: after as Record<string, unknown> | null,
  });
  it.each([
    [line("opportunity.changed"), "Updated from the official source"],
    [line("opportunity.archived"), "No longer listed"],
    [
      line("match.recalculated", { fit_status: "possible" }, { fit_status: "confirmed" }),
      "Fit changed: Possible → Confirmed",
    ],
    [
      line("decision.changed", { decision: "none" }, { decision: "not_for_us" }),
      "Decision: Not for us",
    ],
    [line("decision.changed", { decision: "later" }, { decision: "none" }), "Decision cleared"],
    [
      line(
        "decision.changed",
        { decision: "not_for_us" },
        { decision: "not_for_us", reason: "too_much_work" },
      ),
      "Decision: Not for us (too much work)",
    ],
    [line("application.started"), "Application started"],
    [line("application.submitted"), "Application marked as submitted"],
    [line("application.archived_not_eligible"), "Application archived: no longer eligible"],
    [line("something.new"), "something.new"],
  ])("%o → %s", (h, sentence) => {
    expect(historySentence(h)).toBe(sentence);
  });
});

describe("missing facts point to the Profile", () => {
  it("links a missing company fact to the facts, and a founder fact to the private founders section", async () => {
    show(
      detail({
        requirements: [
          {
            hard: true,
            quote: "TRL 5 or higher",
            fact: "trl",
            criterion: "TRL 5 or higher",
            result: "unknown",
          },
          {
            hard: true,
            quote: "Founders under 35",
            fact: "founder_age",
            criterion: "Founders under 35",
            result: "unknown",
          },
          {
            hard: true,
            quote: "Led by a woman",
            fact: "woman_ceo",
            criterion: "Led by a woman",
            result: "pass",
          },
        ],
      }),
    );
    expect(
      await screen.findByRole("link", { name: "needs your technology readiness level" }),
    ).toHaveAttribute("href", "/profile#facts");
    expect(
      screen.getByRole("link", { name: "add the youngest founder's age (optional, private)" }),
    ).toHaveAttribute("href", "/profile#founders");
    expect(screen.queryByRole("link", { name: /woman CEO/ })).not.toBeInTheDocument();
  });
});

describe("why it fits (D-82)", () => {
  it("shows the calculated fit in words, marked as AI, next to the fit itself", async () => {
    const calls = show(detail(), {
      [`POST /opportunities/${ID}/why-it-fits`]: () => ({
        text: "May fit: add your TRL, the call asks for TRL 5 or higher.",
      }),
    }).calls;
    const card = (await screen.findByRole("heading", { name: "Why it fits" })).closest("div");
    if (!card?.parentElement) throw new Error("no card");
    expect(within(card).getByText("AI")).toBeInTheDocument();
    expect(
      await screen.findByText("May fit: add your TRL, the call asks for TRL 5 or higher."),
    ).toBeInTheDocument();
    expect(screen.getByText("Possible")).toBeInTheDocument(); // the fit is the rules', unchanged
    expect(calls.filter((c) => c.url.endsWith("/why-it-fits"))).toHaveLength(1);
  });

  it("leaves the words out when they cannot be worked out", async () => {
    show(detail(), {
      [`POST /opportunities/${ID}/why-it-fits`]: () => problem(502, "Bad Gateway", "no"),
    });
    await screen.findByText("Eligibility, checked against your facts");
    await waitFor(() =>
      expect(screen.queryByRole("heading", { name: "Why it fits" })).not.toBeInTheDocument(),
    );
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("asks for nothing when the call lists no requirements", async () => {
    const { calls } = show(detail({ requirements: [] }));
    await screen.findByText("The call lists no requirements we could check.");
    expect(calls.some((c) => c.url.endsWith("/why-it-fits"))).toBe(false);
  });
});
