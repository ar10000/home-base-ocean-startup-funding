import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { components } from "../src/api/schema";
import { fakeApi, onboardedMe, problem } from "./fake-api";
import { renderAt } from "./render";

type Fact = components["schemas"]["FactOut"];
type Today = components["schemas"]["Today"];

const today = (goals: Today["current_goal"] = null): Today => ({
  stage: null,
  mode: "preparing",
  one_thing: null,
  needs_attention: [],
  next_deadline: null,
  next_opening: null,
  opening_soon: [],
  top_fact: null,
  current_goal: goals,
});

/** A short version of the API's lists (REQ-09); the real ones live in config.FACT_VALUES. */
const OPTIONS = {
  country: [
    { value: "PT", label: "Portugal" },
    { value: "ES", label: "Spain" },
    { value: "OTHER", label: "Outside the EU" },
  ],
  sector: [
    {
      value: "marine_living_resources",
      label: "Marine living resources (fisheries, aquaculture, seaweed)",
    },
    { value: "blue_biotechnology", label: "Blue biotechnology" },
  ],
  legal_form: [
    { value: "private_limited", label: "Private limited company (Lda, Unipessoal Lda)" },
  ],
  applicant_form: [
    { value: "alone", label: "Alone" },
    { value: "consortium", label: "In a consortium" },
  ],
};

const STAGES = [
  "Idea",
  "Validation",
  "Foundations",
  "Prototype",
  "Pilot",
  "Non-dilutive funding",
  "Raise prep",
  "First round",
  "Growth",
].map((label) => ({ value: label.toLowerCase().replaceAll(" ", "_").replace("-", "_"), label }));

/** A small in-memory profile API: facts are versions; approve marks one approved. */
function serve(initial: Fact[] = [], goals: Today["current_goal"] = null) {
  let facts = [...initial];
  let intent = goals;
  let stage: string | null = null;
  const writes: { path: string; body: unknown }[] = [];
  fakeApi({
    "GET /me": () => onboardedMe,
    "GET /profile": () => ({ facts, founder_facts: [], stage }),
    "GET /stages": () => STAGES,
    "PUT /stage": async (r) => {
      const body = (await r.json()) as { stage: string };
      writes.push({ path: "PUT /stage", body });
      stage = body.stage;
      return new Response(null, { status: 204 });
    },
    "GET /fact-options": () => OPTIONS,
    "GET /today": () => today(intent),
    "POST /facts": async (r) => {
      const body = (await r.json()) as { key: string; value: Fact["value"]; label: Fact["label"] };
      writes.push({ path: "POST /facts", body });
      const fact: Fact = {
        id: `v${writes.length}`,
        key: body.key,
        value: body.value,
        label: body.label,
        approved: false,
        source: null,
        recorded_at: "2026-11-16T10:00:00Z",
      };
      facts = [...facts.filter((f) => f.key !== body.key), fact];
      return fact;
    },
    "POST /facts/v1/approve": () => {
      writes.push({ path: "approve v1", body: null });
      facts = facts.map((f) => (f.id === "v1" ? { ...f, approved: true } : f));
      return facts.find((f) => f.id === "v1");
    },
    "PUT /intent": async (r) => {
      const body = (await r.json()) as { goals: { goal: string; window: string }[] };
      writes.push({ path: "PUT /intent", body });
      intent = body.goals;
      return { goals: body.goals, recorded_at: "2026-11-16T10:00:00Z" };
    },
  });
  return writes;
}

const row = (name: string) => {
  const card = screen.getByText(name, { selector: "span.font-semibold" }).closest("section");
  if (!card) throw new Error(`no card for ${name}`);
  return within(card);
};

const optionsOf = (name: string) =>
  within(row(name).getByLabelText(name))
    .getAllByRole("option")
    .map((o) => o.textContent);

async function facts() {
  await screen.findByRole("heading", { name: "Company facts" });
  await screen.findByLabelText("Country");
}

describe("Profile: company facts, all chosen from lists (D-74, D-76)", () => {
  it("lists the seven hard-rule facts in the spec's words, none given yet", async () => {
    serve();
    renderAt("/profile");
    await facts();
    for (const name of [
      "Country",
      "Sector",
      "Legal form",
      "Company age",
      "Team size",
      "Technology readiness level",
      "Consortium need",
    ]) {
      expect(row(name).getByText("Not given yet")).toBeInTheDocument();
      expect(row(name).getByLabelText(name).tagName).toBe("SELECT");
    }
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("offers the API's lists for country, sector, legal form and consortium need", async () => {
    serve();
    renderAt("/profile");
    await facts();
    expect(optionsOf("Country")).toEqual(["Choose…", "Portugal", "Spain", "Outside the EU"]);
    expect(optionsOf("Sector")).toContain("Blue biotechnology");
    expect(optionsOf("Consortium need")).toEqual(["Choose…", "Alone", "In a consortium"]);
  });

  it("offers fixed ranges for the numbers, TRL with its meaning", async () => {
    serve();
    renderAt("/profile");
    await facts();
    const trl = optionsOf("Technology readiness level");
    expect(trl).toHaveLength(10);
    expect(trl[1]).toBe("TRL 1 · basic principles observed");
    expect(trl[9]).toBe("TRL 9 · actual system proven in an operational environment");
    const age = optionsOf("Company age");
    expect([age[1], age[2], age.at(-1)]).toEqual(["Less than 1 year", "1 year", "50 years"]);
    const team = optionsOf("Team size");
    expect([team[1], team.at(-1)]).toEqual(["1 person", "100 people"]);
  });

  it("saves the chosen value with its type, entered by the founder, then approves it", async () => {
    const writes = serve();
    renderAt("/profile");
    await facts();
    const save = row("Team size").getByRole("button", { name: "Save" });
    expect(save).toBeDisabled();
    fireEvent.change(row("Team size").getByLabelText("Team size"), { target: { value: "4" } });
    fireEvent.click(save);
    expect(
      await screen.findByText("Saved, not approved yet: matching does not use it."),
    ).toBeInTheDocument();
    expect(writes[0]).toEqual({
      path: "POST /facts",
      body: { key: "team_size", value: 4, label: "user_provided" },
    });
    expect(row("Team size").getByText("4 people", { selector: "span" })).toBeInTheDocument();
    fireEvent.click(row("Team size").getByRole("button", { name: "Approve" }));
    expect(await row("Team size").findByText("Approved")).toBeInTheDocument();
  });

  it("sends a listed value as the API's word, and shows it by its label", async () => {
    const writes = serve();
    renderAt("/profile");
    await facts();
    fireEvent.change(row("Country").getByLabelText("Country"), { target: { value: "PT" } });
    fireEvent.click(row("Country").getByRole("button", { name: "Save" }));
    await waitFor(() => expect(writes).toHaveLength(1));
    expect(writes[0]?.body).toEqual({ key: "country", value: "PT", label: "user_provided" });
    expect(await row("Country").findByText("Portugal", { selector: "span" })).toBeInTheDocument();
  });

  it("shows a saved value it does not list as it is", async () => {
    serve([
      {
        id: "v0",
        key: "sector",
        value: "old free text",
        label: "user_provided",
        approved: true,
        source: null,
        recorded_at: "2026-11-15T10:00:00Z",
      },
    ]);
    renderAt("/profile");
    await facts();
    expect(row("Sector").getByText("old free text")).toBeInTheDocument();
  });

  it("shows the API's reason when a fact is refused", async () => {
    fakeApi({
      "GET /me": () => onboardedMe,
      "GET /profile": () => ({ facts: [], founder_facts: [], stage: null }),
      "GET /stages": () => STAGES,
      "GET /fact-options": () => OPTIONS,
      "GET /today": () => today(),
      "POST /facts": () => problem(422, "Unprocessable", "not one of the values for sector"),
    });
    renderAt("/profile");
    await facts();
    fireEvent.change(row("Sector").getByLabelText("Sector"), {
      target: { value: "blue_biotechnology" },
    });
    fireEvent.click(row("Sector").getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("not one of the values for sector");
  });

  it("says so when the lists cannot be loaded", async () => {
    fakeApi({
      "GET /me": () => onboardedMe,
      "GET /profile": () => ({ facts: [], founder_facts: [], stage: null }),
      "GET /stages": () => STAGES,
      "GET /fact-options": () => problem(503, "Unavailable", "lists unavailable"),
      "GET /today": () => today(),
    });
    renderAt("/profile");
    expect(await screen.findByRole("alert")).toHaveTextContent("lists unavailable");
  });
});

describe("Profile: goals (spec: Intent)", () => {
  it("shows the current goals with their windows, and saves a change", async () => {
    const writes = serve([], [{ goal: "investment", window: "later" }]);
    renderAt("/profile#goals");
    const investment = await screen.findByLabelText("Investment");
    await waitFor(() => expect(investment).toBeChecked());
    expect(screen.getByRole("button", { name: "Save goals" })).toBeDisabled();
    fireEvent.click(screen.getByLabelText("Pilot or test site"));
    fireEvent.click(screen.getByRole("button", { name: "Save goals" }));
    await waitFor(() => expect(writes).toHaveLength(1));
    expect(writes[0]?.body).toEqual({
      goals: [
        { goal: "investment", window: "later" },
        { goal: "pilot_or_test_site", window: "soon" },
      ],
    });
    expect(await screen.findByText("Saved")).toBeInTheDocument();
  });

  it("changes a goal's window, and asks for at least one goal (INT-01)", async () => {
    const writes = serve([], [{ goal: "first_customers", window: "now" }]);
    renderAt("/profile");
    await waitFor(() => expect(screen.getByLabelText("First customers")).toBeChecked());
    fireEvent.change(screen.getByLabelText("When"), { target: { value: "later" } });
    fireEvent.click(screen.getByRole("button", { name: "Save goals" }));
    await waitFor(() => expect(writes).toHaveLength(1));
    expect(writes[0]?.body).toEqual({ goals: [{ goal: "first_customers", window: "later" }] });
    fireEvent.click(screen.getByLabelText("First customers"));
    expect(screen.getByRole("button", { name: "Save goals" })).toBeDisabled();
    expect(screen.getByText("Choose at least one goal.")).toBeInTheDocument();
    expect(writes).toHaveLength(1);
  });
});

describe("Profile: about the founders (spec: Founder facts)", () => {
  type FounderFact = components["schemas"]["FounderFactOut"];

  function serveFounders(initial: FounderFact[] = []) {
    let founders = [...initial];
    const writes: { path: string; body: unknown }[] = [];
    fakeApi({
      "GET /me": () => onboardedMe,
      "GET /profile": () => ({ facts: [], founder_facts: founders }),
      "GET /today": () => today(),
      "PUT /founder-facts/woman_ceo": async (r) => {
        const body = (await r.json()) as { value: boolean };
        writes.push({ path: "PUT woman_ceo", body });
        founders = [
          ...founders.filter((f) => f.key !== "woman_ceo"),
          { key: "woman_ceo", value: body.value, approved: false },
        ];
        return founders.at(-1);
      },
      "POST /founder-facts/woman_ceo/approve": () => {
        writes.push({ path: "approve woman_ceo", body: null });
        founders = founders.map((f) => (f.key === "woman_ceo" ? { ...f, approved: true } : f));
        return founders.find((f) => f.key === "woman_ceo");
      },
      "DELETE /founder-facts/youngest_founder_birth_date": () => {
        writes.push({ path: "delete birth date", body: null });
        founders = founders.filter((f) => f.key !== "youngest_founder_birth_date");
        return new Response(null, { status: 204 });
      },
      "PUT /founder-facts/youngest_founder_birth_date": async (r) => {
        const body = (await r.json()) as { value: string };
        writes.push({ path: "PUT birth date", body });
        return { key: "youngest_founder_birth_date", value: body.value, approved: false };
      },
    });
    return writes;
  }

  const founderRow = (name: string) => {
    const card = screen.getByText(name, { selector: "span.font-semibold" }).closest("section");
    if (!card) throw new Error(`no card for ${name}`);
    return within(card);
  };

  it("says the facts are optional and private, each with its reason, none given", async () => {
    serveFounders();
    renderAt("/profile#founders");
    await screen.findByRole("heading", { name: "About the founders" });
    expect(screen.getByText(/Optional and private/)).toBeInTheDocument();
    expect(
      founderRow("Youngest founder's birth date").getByText(
        "Some calls are only open to founders under a certain age.",
      ),
    ).toBeInTheDocument();
    for (const name of [
      "Youngest founder's birth date",
      "At least one woman founder",
      "Woman CEO",
    ]) {
      expect(founderRow(name).getByText("Not given")).toBeInTheDocument();
    }
  });

  it("saves a yes/no fact, then approves it", async () => {
    const writes = serveFounders();
    renderAt("/profile");
    await screen.findByRole("heading", { name: "About the founders" });
    fireEvent.change(founderRow("Woman CEO").getByLabelText("Woman CEO"), {
      target: { value: "yes" },
    });
    fireEvent.click(founderRow("Woman CEO").getByRole("button", { name: "Save" }));
    fireEvent.click(await founderRow("Woman CEO").findByRole("button", { name: "Approve" }));
    expect(await founderRow("Woman CEO").findByText("Approved")).toBeInTheDocument();
    expect(writes).toEqual([
      { path: "PUT woman_ceo", body: { value: true } },
      { path: "approve woman_ceo", body: null },
    ]);
  });

  it("refuses a birth date in the future and sends a past one as a date", async () => {
    const writes = serveFounders();
    renderAt("/profile");
    await screen.findByRole("heading", { name: "About the founders" });
    const row = founderRow("Youngest founder's birth date");
    const save = row.getByRole("button", { name: "Save" });
    fireEvent.change(row.getByLabelText("Youngest founder's birth date"), {
      target: { value: "2999-01-01" },
    });
    expect(save).toBeDisabled();
    fireEvent.change(row.getByLabelText("Youngest founder's birth date"), {
      target: { value: "1995-06-30" },
    });
    fireEvent.click(save);
    await waitFor(() =>
      expect(writes).toEqual([{ path: "PUT birth date", body: { value: "1995-06-30" } }]),
    );
  });

  it("deletes a founder fact, which then shows as not given", async () => {
    const writes = serveFounders([
      { key: "youngest_founder_birth_date", value: "1995-06-30", approved: true },
    ]);
    renderAt("/profile");
    await screen.findByRole("heading", { name: "About the founders" });
    const row = founderRow("Youngest founder's birth date");
    expect(row.getByText("30 Jun 1995")).toBeInTheDocument();
    fireEvent.click(row.getByRole("button", { name: "Delete" }));
    expect(await row.findByText("Not given")).toBeInTheDocument();
    expect(writes).toEqual([{ path: "delete birth date", body: null }]);
  });
});

describe("Profile: where you are (D-78)", () => {
  it("has no stage at first, then saves the one chosen and shows it as n of 9", async () => {
    const writes = serve();
    renderAt("/profile#stage");
    expect(await screen.findByText("No stage chosen yet.")).toBeInTheDocument();
    const select = screen.getByLabelText("Your stage");
    const options = within(select)
      .getAllByRole("option")
      .map((o) => o.textContent);
    expect(options).toHaveLength(10);
    expect(options[6]).toBe("6 · Non-dilutive funding");
    fireEvent.change(select, { target: { value: "non_dilutive_funding" } });
    fireEvent.click(
      within(select.closest("form") as HTMLElement).getByRole("button", { name: "Save" }),
    );
    expect(await screen.findByText("Stage 6 of 9")).toBeInTheDocument();
    expect(writes).toContainEqual({ path: "PUT /stage", body: { stage: "non_dilutive_funding" } });
  });
});
