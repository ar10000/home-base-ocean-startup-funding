// The public demo (D-79): a static build that serves a recorded snapshot of the real API
// instead of calling it. The snapshot was recorded from the local stack, playing a
// fictional founder over fictional calls (scripts/demo/), so every status, date and
// fit shown was computed by the real rules. Nothing is sent anywhere. The recorded AI
// answers can be asked for again; every other change is refused.
import snapshot from "./snapshot.json";

const responses = snapshot as unknown as Record<string, unknown>;

export const DEMO_RECORDED_ON = snapshot.recorded_on;

// The list filters, in the order the snapshot was recorded with.
const QUERY_ORDER = ["fit", "decision"];

function json(status: number, body: unknown, type = "application/json"): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": type } });
}

/** "GET /opportunities?fit=possible" for a request to …/api/opportunities?fit=possible. */
export function snapshotKey(request: Request): string {
  const url = new URL(request.url);
  const path = url.pathname.slice(url.pathname.indexOf("/api") + "/api".length);
  const query = new URLSearchParams();
  for (const name of QUERY_ORDER) {
    const value = url.searchParams.get(name);
    if (value && value !== "null") query.set(name, value);
  }
  return `${request.method} ${path}${query.size ? `?${query}` : ""}`;
}

export function demoFetch(request: Request): Promise<Response> {
  const key = snapshotKey(request);
  // The AI's answers ("Why it fits", "Draft with AI") were recorded from the real app, so
  // a visitor can ask for them; every other change is refused.
  if (request.method === "POST" && key in responses) {
    return Promise.resolve(json(200, responses[key]));
  }
  if (request.method !== "GET") {
    return Promise.resolve(
      json(
        403,
        {
          title: "Read-only demo",
          detail:
            "Changes aren't saved in this demo. Run Home Base locally to try every step (see the README).",
          status: 403,
        },
        "application/problem+json",
      ),
    );
  }
  if (key in responses) return Promise.resolve(json(200, responses[key]));
  return Promise.resolve(
    json(404, { title: "Not found", status: 404 }, "application/problem+json"),
  );
}

export function installDemo(): void {
  globalThis.fetch = (input: RequestInfo | URL, init?: RequestInit) =>
    demoFetch(input instanceof Request ? input : new Request(input, init));
}
