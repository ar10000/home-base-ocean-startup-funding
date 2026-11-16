import type { components } from "../../api/schema";
import { factLabel, formatDate } from "../../lib/format";

export { formatDate, readinessLabel } from "../../lib/format";

export type Task = components["schemas"]["TaskOut"];

// The task sentences, word for word from the spec ("Your one thing today", "Preparing
// mode"). Until week 4 adds the AI wording (marked as AI), Today shows these templates.
// The task itself is always chosen by the API; nothing here decides.
export function taskSentence(task: Task): string {
  const opportunity = task.opportunity ?? "this opportunity";
  switch (task.type) {
    case "add_fact":
      return `Add ${task.fact ? factLabel(task.fact) : "a missing fact"}`;
    case "review_drafts":
      return `Review ${task.count ?? 0} draft answers`;
    case "answer_one_question":
      return `Answer 1 question for ${opportunity}`;
    case "start_application":
      return `Start your ${opportunity} application`;
    case "next_answer":
      // The spec gives no sentence for this task (D-67, awaiting Andrew).
      return task.question
        ? `Work on question ${task.question} of your ${opportunity} application`
        : `Work on your ${opportunity} application`;
    case "decide":
      return task.deadline
        ? `Decide on ${opportunity}: opens ${formatDate(task.deadline)}`
        : `Decide on ${opportunity}`;
    case "back_on_list":
      return `${opportunity} is back on your list`;
    case "check_goals":
      return "Check your goals are still right";
  }
}

/** "About 10 minutes", from the API's fixed table per task type (spec: Time estimate). */
export function minutesLabel(minutes: number): string {
  return `About ${minutes} minutes`;
}
