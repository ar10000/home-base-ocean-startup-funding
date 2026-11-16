import { vi } from "vitest";
import type { components } from "../src/api/schema";

type Handler = (request: Request) => unknown;
/** "GET /me" → handler. A handler returns a JSON body, or a Response for anything else. */
export type Routes = Record<string, Handler>;

export function problem(status: number, title: string, detail?: string): Response {
  return new Response(JSON.stringify({ title, detail, status }), {
    status,
    headers: { "Content-Type": "application/problem+json" },
  });
}

/** Stands in for the API: matches "METHOD /path" (after /api), 404 for anything else. */
export function fakeApi(routes: Routes) {
  const calls: Request[] = [];
  vi.stubGlobal("fetch", async (input: Request) => {
    calls.push(input);
    const path = new URL(input.url).pathname.replace(/^\/api/, "");
    const handler = routes[`${input.method} ${path}`];
    if (!handler) return problem(404, "Not found", `${input.method} ${path}`);
    const result = await handler(input);
    if (result instanceof Response) return result;
    return new Response(JSON.stringify(result), {
      status: input.method === "POST" ? 201 : 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  return calls;
}

export const onboardedMe: components["schemas"]["Me"] = {
  user_id: "00000000-0000-7000-8000-000000000001",
  company_id: "00000000-0000-7000-8000-000000000002",
  given_name: "Inês",
};
