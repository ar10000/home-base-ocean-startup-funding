# Evaluation sets (handbook section 10)

Fictional calls and companies, labelled by hand, to measure each AI task against the
handbook's thresholds. Never real founders' data: these run on Mistral's free tier
(ADR-009), which may use inputs for training.

- `extraction/*.yaml`: a call's text and the hard rules a careful reader finds in it.
  Measured: recall and precision of hard rules (same fact, operator and values) and
  quotes found word for word in the call.
- `drafting/*.yaml`: a question and approved facts. Measured: drafts refused for an
  unsupported number or fact, and length.

Run with `make evals` (needs `HOME_BASE_MISTRAL_API_KEY`); results are written to
`results/`, named by task, prompt version and model, so each change shows its before
and after.
