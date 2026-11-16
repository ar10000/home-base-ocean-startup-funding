import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { Pill } from "../../components/Pill";
import { Empty, ErrorState, Loading } from "../../components/States";
import { api, unwrap } from "../../lib/api";
import { statusLabel } from "./labels";

export function Component() {
  const list = useQuery({
    queryKey: ["applications"],
    queryFn: async () => unwrap(await api.GET("/applications")),
  });
  return (
    <>
      <h1 className="m-0 text-4xl font-semibold tracking-tight">Applications</h1>
      {list.isPending && <Loading label="Loading applications…" />}
      {list.error && <ErrorState error={list.error} onRetry={() => void list.refetch()} />}
      {list.data &&
        (list.data.length === 0 ? (
          <Empty title="No applications yet">
            Start one from an <Link to="/opportunities">opportunity</Link>.
          </Empty>
        ) : (
          <ul aria-label="Applications" className="m-0 flex list-none flex-col gap-3 p-0">
            {list.data.map((a) => (
              <li key={a.id}>
                <Link
                  to={`/applications/${a.id}`}
                  className="flex flex-wrap items-center justify-between gap-3 rounded-card bg-white p-5 text-ink no-underline shadow-card"
                >
                  <span className="flex flex-col gap-0.5">
                    <span className="font-semibold">{a.opportunity}</span>
                    {a.call_removed && (
                      <span className="text-xs text-ink-muted">No longer listed · read only</span>
                    )}
                  </span>
                  <span className="flex items-center gap-3 text-sm text-ink-muted">
                    {a.answers_ready &&
                      `${a.answers_ready.ready} of ${a.answers_ready.total} answers ready`}
                    <Pill
                      tone={
                        a.status === "ready" || a.status === "submitted" ? "confirmed" : "unknown"
                      }
                    >
                      {statusLabel[a.status]}
                    </Pill>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        ))}
    </>
  );
}
