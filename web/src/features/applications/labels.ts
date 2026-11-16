import type { components } from "../../api/schema";

type Schemas = components["schemas"];

/** Spec, Progress: application status. */
export const statusLabel: Record<Schemas["ApplicationStatus"], string> = {
  not_started: "Not started",
  in_progress: "In progress",
  ready: "Ready",
  submitted: "Submitted",
};

/** Spec, Application: each question as missing facts, AI draft, edited or approved. */
export const answerStateLabel: Record<Schemas["AnswerState"], string> = {
  missing_facts: "Missing facts",
  ai_draft: "AI draft",
  edited: "Edited",
  approved: "Approved",
};
