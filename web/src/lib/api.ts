// The one place the web app talks to the API (handbook section 2). Types come from the
// generated schema in src/api/, which is never edited by hand (`make client`).
import createClient, { type Middleware } from "openapi-fetch";
import type { paths } from "../api/schema";

/** Returns the signed-in user's access token, or null before sign-in. Set by the sign-in layer. */
let tokenProvider: () => Promise<string | null> = async () => null;

export function setTokenProvider(provider: () => Promise<string | null>): void {
  tokenProvider = provider;
}

/** An RFC 9457 problem from the API, raised so TanStack Query shows the error state. */
export class ApiProblem extends Error {
  readonly status: number;
  readonly title: string;
  readonly detail: string | undefined;

  constructor(status: number, title: string, detail?: string) {
    super(detail ?? title);
    this.status = status;
    this.title = title;
    this.detail = detail;
  }
}

const auth: Middleware = {
  async onRequest({ request }) {
    const token = await tokenProvider();
    if (token) request.headers.set("Authorization", `Bearer ${token}`);
    return request;
  },
};

// Looked up on each call (not captured once), so tests can stand in for the API.
export const api = createClient<paths>({
  baseUrl: `${globalThis.location?.origin ?? ""}/api`,
  fetch: (request) => globalThis.fetch(request),
});
api.use(auth);

type Problem = { title?: string; detail?: string };

/** Unwraps an openapi-fetch result: the data (undefined for 204 No Content), or an ApiProblem. */
export function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.error !== undefined || !result.response.ok) {
    const problem = (result.error ?? {}) as Problem;
    throw new ApiProblem(
      result.response.status,
      problem.title ?? result.response.statusText,
      problem.detail,
    );
  }
  return result.data as T;
}
