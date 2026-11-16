// Display wording shared by screens. Each label is the spec's own wording, cited beside it;
// the values come from the API, which does every calculation.
import type { components } from "../api/schema";

type Schemas = components["schemas"];

const LISBON = "Europe/Lisbon";
const dayMonth = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  timeZone: LISBON,
});
const monthYear = new Intl.DateTimeFormat("en-GB", {
  month: "long",
  year: "numeric",
  timeZone: LISBON,
});

/** "21 Nov", for an ISO calendar date. Noon UTC keeps the day the same in Lisbon. */
export function formatDate(iso: string): string {
  return dayMonth.format(new Date(`${iso}T12:00:00Z`));
}

/** "March 2027", for a YYYY-MM month. */
export function formatMonth(yearMonth: string): string {
  return monthYear.format(new Date(`${yearMonth}-15T12:00:00Z`));
}

/** Spec, Opportunities: Fit. */
export const fitLabel: Record<Schemas["FitStatus"], string> = {
  confirmed: "Confirmed",
  possible: "Possible",
  not_eligible: "Not eligible",
};

/** Spec, Founder decisions. "none" has no label: no decision is the default. */
export const decisionLabel: Record<Schemas["Decision"], string | null> = {
  none: null,
  pursuing: "Pursuing",
  later: "Later",
  not_for_us: "Not for us",
};

/** Spec, Opportunities: Scope label. */
export const scopeLabel: Record<Schemas["Scope"], string> = {
  blue_specific: "Blue-specific",
  all_sectors: "Open to all sectors",
};

/** Spec, Opportunities: Deadline (SCP-03): days left when 30 or fewer, else a date; Rolling. */
export function deadlineLabel(d: Schemas["Deadline"]): string {
  if (d.kind === "rolling" || d.date === null) return "Rolling";
  if (d.kind === "days_left" && d.days_left !== null) {
    return d.days_left === 1 ? "1 day left" : `${d.days_left} days left`;
  }
  return formatDate(d.date);
}

/** Spec, Upcoming opportunities: "Opens [date]" when official, "Expected around [month]". */
export function openingLabel(opening: string | null, expectedMonth: string | null): string | null {
  if (opening) return `Opens ${formatDate(opening)}`;
  if (expectedMonth) return `Expected around ${formatMonth(expectedMonth)}`;
  return null;
}

/** Spec, Readiness: "Ready for n of m questions". */
export function readinessLabel(r: Schemas["Readiness"]): string {
  return `Ready for ${r.ready} of ${r.total} questions`;
}

/** Spec, Opportunities: "Checked X ago" (D-68 for the exact words). */
export function checkedLabel(daysAgo: number): string {
  if (daysAgo <= 0) return "Checked today";
  if (daysAgo === 1) return "Checked yesterday";
  return `Checked ${daysAgo} days ago`;
}

/** Spec, Intent: the opportunity types, in the spec's words. */
const typeLabels: Record<string, string> = {
  grant: "Grant",
  accelerator: "Accelerator or incubator",
  testbed_or_pilot: "Testbed or pilot programme",
  procurement_challenge: "Procurement or innovation challenge",
  prize: "Prize or competition",
  investor_programme: "Investor programme",
};

export function typesLabel(types: readonly string[]): string {
  return types.map((t) => typeLabels[t] ?? t).join(", ");
}

/** Spec, Requirement types: the hard-rule facts, in the spec's words (D-47 keys). */
const factLabels: Record<string, string> = {
  country: "country",
  sector: "sector",
  legal_form: "legal form",
  company_age: "company age",
  team_size: "team size",
  trl: "technology readiness level",
  applicant_form: "consortium need",
  // Founder facts (spec: Founder facts); a call checks the age worked out from the birth date.
  founder_age: "youngest founder's age",
  youngest_founder_birth_date: "youngest founder's birth date",
  woman_founder: "at least one woman founder",
  woman_ceo: "woman CEO",
};

/** The founder facts a call can check (spec: Founder facts), and the stored fact behind each. */
export const FOUNDER_FACT_FOR: Record<string, string> = {
  founder_age: "youngest_founder_birth_date",
  woman_founder: "woman_founder",
  woman_ceo: "woman_ceo",
};

/** A fact's name for a sentence; an uncatalogued key reads with spaces. */
export function factLabel(key: string): string {
  return factLabels[key] ?? key.replaceAll("_", " ");
}

/** Spec, Intent: the goals, in the spec's words. */
export const goalLabel: Record<string, string> = {
  pilot_or_test_site: "Pilot or test site",
  non_dilutive_funding: "Non-dilutive funding",
  accelerator_place: "Accelerator or incubator place",
  first_customers: "First customers",
  investment: "Investment",
};

/** Spec, Intent: each goal's window. */
export const windowLabel: Record<string, string> = {
  now: "now (within 3 months)",
  soon: "soon (3 to 6 months)",
  later: "later (6 to 12 months)",
};
