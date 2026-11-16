import type { ReactNode } from "react";

// The fixed status colours (spec): sea green confirmed, warm sand deadlines, grey unknown,
// coral AI. Nothing else picks a colour for a status.
const tones = {
  confirmed: "bg-mist text-sea-deep",
  deadline: "bg-deadline text-deadline-ink",
  unknown: "bg-unknown text-unknown-ink",
  ai: "bg-coral-soft text-ink",
} as const;

export type Tone = keyof typeof tones;

export function Pill({ tone, children }: { tone: Tone; children: ReactNode }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold whitespace-nowrap ${tones[tone]}`}
    >
      {children}
    </span>
  );
}
