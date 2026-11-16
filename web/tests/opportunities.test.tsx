import { fireEvent, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { components } from "../src/api/schema";
import {
  checkedLabel,
  deadlineLabel,
  factLabel,
  formatDate,
  formatMonth,
  openingLabel,
  typesLabel,
} from "../src/lib/format";
import { fakeApi, onboardedMe, problem } from "./fake-api";
import { renderAt } from "./render";

type Item = components["schemas"]["OpportunityItem"];
type List = components["schemas"]["OpportunityList"];

const item = (over: Partial<Item>): Item => ({
  id: "00000000-0000-7000-8000-0000000000a1",
  name: "Blue Bio Value",
  funder: "Fundação Oceano Azul",
  types: ["accelerator"],
  scope: "blue_specific",
  status: "open",
  fit: { status: "confirmed", few_explicit_rules: false },
  deadline: { kind: "days_left", date: "2026-11-21", days_left: 12 },
  opening: null,
  expected_month: null,
  based_on_last_edition: false,
  readiness: null,
  decision: "none",
  goal_relevant: true,
  checked_days_ago: 2,
  checked_on: "2026-11-07",
  recheck_due: false,
  ...over,
});

const counts = { confirmed: 1, possible: 2, not_eligible: 3 };

function showList(list: List | ((url: URL) => List | Response)) {
  const seen: URL[] = [];
  fakeApi({
    "GET /me": () => onboardedMe,
    "GET /opportunities": (request) => {
      const url = new URL(request.url);
      seen.push(url);
      return typeof list === "function" ? list(url) : list;
    },
  });
  return seen;
}

describe("Opportunities list", () => {
  it("shows a loading state, then an error with retry", async () => {
    showList(() => problem(500, "Server error", "list failed"));
    renderAt("/opportunities");
    expect(await screen.findByRole("alert")).toHaveTextContent("list failed");
  });

  it("with no matches says so, without filters", async () => {
    showList({ items: [], counts: { confirmed: 0, possible: 0, not_eligible: 0 } });
    renderAt("/opportunities");
    expect(await screen.findByText("No matches yet")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "All 0" })).toHaveAttribute("aria-pressed", "true");
  });

  it("counts All as confirmed plus possible, since the default list leaves out Not eligible", async () => {
    showList({ items: [item({})], counts });
    renderAt("/opportunities");
    expect(await screen.findByRole("button", { name: "All 3" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Confirmed 1" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Possible 2" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Not eligible 3" })).toBeInTheDocument();
  });

  it("sends the fit and decision filters to the API and keeps them in the address", async () => {
    const seen = showList(() => ({ items: [], counts }));
    const router = renderAt("/opportunities");
    fireEvent.click(await screen.findByRole("button", { name: "Not eligible 3" }));
    fireEvent.change(screen.getByLabelText("Decision"), { target: { value: "not_for_us" } });
    expect(await screen.findByText("Nothing matches these filters")).toBeInTheDocument();
    const last = seen.at(-1);
    expect(last?.searchParams.get("fit")).toBe("not_eligible");
    expect(last?.searchParams.get("decision")).toBe("not_for_us");
    expect(router.state.location.search).toBe("?fit=not_eligible&decision=not_for_us");
    fireEvent.click(screen.getByRole("button", { name: "All 3" }));
    expect(router.state.location.search).toBe("?decision=not_for_us");
  });

  it("ignores an unknown filter in the address", async () => {
    const seen = showList(() => ({ items: [], counts }));
    renderAt("/opportunities?fit=bogus&decision=maybe");
    await screen.findByText("No matches yet");
    expect(seen[0]?.search).toBe("");
  });

  it("shows each item's fit, deadline, scope, check age, readiness and decision", async () => {
    showList({
      items: [
        item({
          readiness: { ready: 6, total: 8 },
          decision: "pursuing",
          fit: { status: "possible", few_explicit_rules: true },
          recheck_due: true,
        }),
      ],
      counts,
    });
    renderAt("/opportunities");
    const link = await screen.findByRole("link", { name: /Blue Bio Value/ });
    expect(link).toHaveAttribute("href", "/opportunities/00000000-0000-7000-8000-0000000000a1");
    const row = within(link);
    expect(
      row.getByText("Accelerator or incubator · Blue-specific · Checked 2 days ago"),
    ).toBeInTheDocument();
    expect(row.getByText("Ready for 6 of 8 questions")).toBeInTheDocument();
    expect(row.getByText("Possible · few explicit rules")).toBeInTheDocument();
    expect(row.getByText("12 days left")).toBeInTheDocument();
    expect(row.getByText("Pursuing")).toBeInTheDocument();
    expect(row.getByText("Re-check due")).toBeInTheDocument();
  });

  it("shows an upcoming call by its opening, labelled when based on the last edition", async () => {
    showList({
      items: [
        item({
          status: "upcoming",
          deadline: { kind: "date", date: "2027-04-30", days_left: null },
          expected_month: "2027-03",
          based_on_last_edition: true,
        }),
      ],
      counts,
    });
    renderAt("/opportunities");
    expect(
      await screen.findByText(`Expected around ${formatMonth("2027-03")}`),
    ).toBeInTheDocument();
    expect(screen.getByText("based on last edition")).toBeInTheDocument();
    expect(screen.queryByText(formatDate("2027-04-30"))).not.toBeInTheDocument();
  });

  it("puts goal-relevant matches first and the rest under Other matches", async () => {
    showList({
      items: [item({ name: "Relevant" }), item({ id: "b", name: "Other", goal_relevant: false })],
      counts,
    });
    renderAt("/opportunities");
    const other = await screen.findByRole("list", { name: "Other matches" });
    expect(within(other).getByText("Other")).toBeInTheDocument();
    expect(
      within(screen.getByRole("list", { name: "Matched opportunities" })).getByText("Relevant"),
    ).toBeInTheDocument();
  });

  it("shows no Other matches heading when no goal makes any match relevant", async () => {
    showList({ items: [item({ goal_relevant: false })], counts });
    renderAt("/opportunities");
    await screen.findByRole("list", { name: "Matched opportunities" });
    expect(screen.queryByRole("heading", { name: "Other matches" })).not.toBeInTheDocument();
  });
});

describe("display wording (spec)", () => {
  it.each([
    [{ kind: "rolling", date: null, days_left: null }, "Rolling"],
    [{ kind: "days_left", date: "2026-11-16", days_left: 0 }, "0 days left"],
    [{ kind: "days_left", date: "2026-11-17", days_left: 1 }, "1 day left"],
    [{ kind: "days_left", date: "2026-12-16", days_left: 30 }, "30 days left"],
    [{ kind: "date", date: "2026-12-17", days_left: null }, formatDate("2026-12-17")],
  ] as const)("deadline %o → %s (SCP-03)", (deadline, label) => {
    expect(deadlineLabel(deadline)).toBe(label);
  });

  it("shows an official opening before an expected month, and nothing with neither", () => {
    expect(openingLabel("2027-01-12", "2027-01")).toBe(`Opens ${formatDate("2027-01-12")}`);
    expect(openingLabel(null, "2027-02")).toBe(`Expected around ${formatMonth("2027-02")}`);
    expect(openingLabel(null, null)).toBeNull();
  });

  it("formats dates in Lisbon time without shifting the day", () => {
    expect(formatDate("2026-12-31")).toBe("31 Dec");
    expect(formatMonth("2027-03")).toBe("March 2027");
  });

  it.each([
    [0, "Checked today"],
    [1, "Checked yesterday"],
    [14, "Checked 14 days ago"],
  ])("checked %i days ago → %s", (days, label) => {
    expect(checkedLabel(days)).toBe(label);
  });

  it("names facts in the spec's words, and an uncatalogued key with spaces", () => {
    expect(factLabel("trl")).toBe("technology readiness level");
    expect(factLabel("applicant_form")).toBe("consortium need");
    expect(factLabel("founder_birth_date")).toBe("founder birth date");
  });

  it("names every type in the spec's words, and keeps an unknown one as is", () => {
    expect(typesLabel(["procurement_challenge", "prize", "new_kind"])).toBe(
      "Procurement or innovation challenge, Prize or competition, new_kind",
    );
  });
});
