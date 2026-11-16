import type { ReactNode } from "react";
import { ApiProblem } from "../lib/api";

// Shared loading, error and empty states (plan, week 3: "Empty, loading and error states
// for each screen"). Screens pass their own words; these only give the shape.

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <section className={`rounded-card bg-white p-6 shadow-card ${className}`}>{children}</section>
  );
}

export function Loading({ label }: { label: string }) {
  return (
    <div role="status" aria-live="polite" className="text-sm text-ink-muted">
      {label}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const message =
    error instanceof ApiProblem ? (error.detail ?? error.title) : "Home Base could not be reached.";
  return (
    <Card>
      <div role="alert" className="flex flex-col items-start gap-3">
        <p className="m-0 font-semibold">Something went wrong</p>
        <p className="m-0 text-sm text-ink-muted">{message}</p>
        {onRetry && (
          <button type="button" onClick={onRetry} className="btn-secondary">
            Try again
          </button>
        )}
      </div>
    </Card>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <Card>
      <p className="m-0 font-semibold">{title}</p>
      {children && <div className="mt-2 text-sm text-ink-muted">{children}</div>}
    </Card>
  );
}
