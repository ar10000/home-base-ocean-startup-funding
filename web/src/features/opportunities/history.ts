import type { components } from "../../api/schema";
import { decisionLabel, fitLabel } from "../../lib/format";

type HistoryLine = components["schemas"]["HistoryLine"];
type FitStatus = components["schemas"]["FitStatus"];
type Decision = components["schemas"]["Decision"];
type Reason = components["schemas"]["NotForUsReason"];

/** Spec, Founder decisions: the optional reasons for Not for us, in sentence case. */
export const reasonLabel: Record<Reason, string> = {
  not_relevant: "Not relevant",
  too_early: "Too early",
  too_much_work: "Too much work",
  other: "Other",
};

function fit(fields: HistoryLine["before"]): string | null {
  const status = fields?.["fit_status"] as FitStatus | undefined;
  return status ? fitLabel[status] : null;
}

/** One line of an opportunity's history, from its audit event (D-69). */
export function historySentence(h: HistoryLine): string {
  switch (h.action) {
    case "opportunity.added":
      return "Added from the official source";
    case "opportunity.changed":
      return "Updated from the official source";
    case "opportunity.archived":
      return "No longer listed";
    case "match.recalculated": {
      const before = fit(h.before);
      const after = fit(h.after) ?? "unknown";
      return before ? `Fit changed: ${before} → ${after}` : `Matched to your company: ${after}`;
    }
    case "decision.changed": {
      const after = h.after?.["decision"] as Decision | undefined;
      const label = after ? decisionLabel[after] : null;
      const reason = h.after?.["reason"] as Reason | null | undefined;
      if (!label) return "Decision cleared";
      return reason
        ? `Decision: ${label} (${reasonLabel[reason].toLowerCase()})`
        : `Decision: ${label}`;
    }
    case "application.started":
      return "Application started";
    case "application.submitted":
      return "Application marked as submitted";
    case "application.archived_not_eligible":
      return "Application archived: no longer eligible";
    default:
      return h.action;
  }
}
