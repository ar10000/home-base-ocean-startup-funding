import type { ReactNode } from "react";

export function PageHeading({ eyebrow, children }: { eyebrow?: string; children: ReactNode }) {
  return (
    <header>
      {eyebrow && (
        <div className="text-xs font-semibold tracking-[0.08em] text-ink-muted uppercase">
          {eyebrow}
        </div>
      )}
      <h1 className="mt-1.5 text-4xl font-semibold tracking-tight">{children}</h1>
    </header>
  );
}
