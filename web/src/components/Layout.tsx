import { NavLink, Outlet } from "react-router";
import { AuthGate } from "../features/account/AuthGate";

// The left navigation from the Calm tide wireframes. Only Phase 1 screens are listed; the
// wireframes' Journey and Search are not in Phase 1 scope. Profile holds facts and goals (D-74).
const items = [
  { to: "/", label: "Today", end: true },
  { to: "/opportunities", label: "Opportunities", end: false },
  { to: "/applications", label: "Applications", end: false },
  { to: "/profile", label: "Profile", end: false },
] as const;

function navClass({ isActive }: { isActive: boolean }): string {
  const base =
    "flex min-h-11 items-center rounded-nav px-3.5 text-sm no-underline hover:text-sea-deep";
  return isActive ? `${base} bg-mist font-semibold text-sea-deep` : `${base} text-ink`;
}

export function Layout() {
  return (
    <div className="flex min-h-screen flex-wrap">
      <nav aria-label="Main" className="flex flex-[1_1_210px] flex-col gap-1 px-4 py-6">
        <div className="flex items-center gap-2.5 px-3 pt-1 pb-6">
          <span
            aria-hidden="true"
            className="flex size-8 items-center justify-center rounded-[10px] bg-sea"
          >
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="#fff"
              strokeWidth="2"
              strokeLinecap="round"
            >
              <path d="M3 15c2.5 0 2.5-2 5-2s2.5 2 5 2 2.5-2 5-2 2.5 2 3 2" />
              <path d="M3 10c2.5 0 2.5-2 5-2s2.5 2 5 2 2.5-2 5-2 2.5 2 3 2" />
            </svg>
          </span>
          <span className="text-base font-bold">Home Base</span>
        </div>
        {items.map((item) => (
          <NavLink key={item.to} to={item.to} end={item.end} className={navClass}>
            {item.label}
          </NavLink>
        ))}
      </nav>
      <main className="flex min-w-0 max-w-[1120px] flex-[999_1_600px] flex-col gap-6 px-4 pt-9 pb-14 sm:px-9">
        {import.meta.env.VITE_DEMO === "1" && <DemoNotice />}
        <AuthGate>
          <Outlet />
        </AuthGate>
      </main>
    </div>
  );
}

/** The public demo says what it is (D-79): fictional data, a snapshot, nothing saved. */
function DemoNotice() {
  return (
    <p role="note" className="m-0 rounded-xl border border-line bg-mist px-4 py-3 text-sm text-ink">
      <strong>Demo.</strong> A fictional founder and fictional calls, recorded from the real app.
      Every fit, date and task was worked out by its rules. Changes aren&rsquo;t saved.
    </p>
  );
}
