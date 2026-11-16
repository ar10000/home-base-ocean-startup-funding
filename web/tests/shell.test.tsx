import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { makeQueryClient } from "../src/App";
import { ApiProblem, unwrap } from "../src/lib/api";
import { fakeApi, onboardedMe } from "./fake-api";
import { renderAt } from "./render";

describe("app shell", () => {
  beforeEach(() => {
    fakeApi({ "GET /me": () => onboardedMe });
  });

  it.each([
    ["/", /^Good (morning|afternoon|evening), Inês$/],
    ["/opportunities", "Opportunities"],
    ["/applications", "Applications"],
  ])("routes %s to its screen (%s)", async (path, heading) => {
    renderAt(path);
    expect(await screen.findByRole("heading", { level: 1, name: heading })).toBeInTheDocument();
  });

  it("marks only the current screen in the navigation", async () => {
    renderAt("/opportunities/abc");
    const nav = await screen.findByRole("navigation", { name: "Main" });
    const current = nav.querySelectorAll('[aria-current="page"]');
    expect(current).toHaveLength(1);
    expect(current[0]).toHaveTextContent("Opportunities");
  });
});

describe("unwrap", () => {
  const response = (status: number, statusText = "") => new Response(null, { status, statusText });

  it("returns the data on success", () => {
    expect(unwrap({ data: { ok: 1 }, response: response(200) })).toEqual({ ok: 1 });
  });

  it("turns an RFC 9457 problem into an ApiProblem with its status and detail", () => {
    const run = () =>
      unwrap({
        error: { title: "Not signed in", detail: "sign in again" },
        response: response(401),
      });
    expect(run).toThrow(ApiProblem);
    try {
      run();
    } catch (e) {
      expect(e).toMatchObject({ status: 401, title: "Not signed in", detail: "sign in again" });
    }
  });

  it("falls back to the HTTP status text when the body is empty", () => {
    expect(() => unwrap({ response: response(502, "Bad Gateway") })).toThrow("Bad Gateway");
  });
});

describe("retry policy", () => {
  const retry = makeQueryClient().getDefaultOptions().queries?.retry as (
    count: number,
    error: unknown,
  ) => boolean;

  it("does not retry a problem the user must fix", () => {
    expect(retry(0, new ApiProblem(401, "Not signed in"))).toBe(false);
    expect(retry(0, new ApiProblem(404, "Not found"))).toBe(false);
  });

  it("retries server and network errors twice", () => {
    expect(retry(0, new ApiProblem(503, "Unavailable"))).toBe(true);
    expect(retry(1, new TypeError("network"))).toBe(true);
    expect(retry(2, new TypeError("network"))).toBe(false);
  });
});
