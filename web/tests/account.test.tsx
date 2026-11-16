import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fakeApi, onboardedMe, problem } from "./fake-api";
import { renderAt } from "./render";

const signinRedirect = vi.fn(async () => undefined);
const signinRedirectCallback = vi.fn(async () => ({}));

vi.mock("../src/lib/auth", async (original) => ({
  ...(await original<typeof import("../src/lib/auth")>()),
  userManager: () => ({ signinRedirect, signinRedirectCallback }),
}));

beforeEach(() => {
  signinRedirect.mockClear();
  signinRedirectCallback.mockReset();
});

describe("sign-in gate (D-64)", () => {
  it("shows a loading state while it checks the sign-in", async () => {
    fakeApi({ "GET /me": () => new Promise(() => {}) });
    renderAt("/");
    expect(await screen.findByRole("status")).toHaveTextContent("Checking your sign-in");
  });

  it("asks a signed-out visitor to sign in, and starts Keycloak's sign-in", async () => {
    fakeApi({ "GET /me": () => problem(401, "Not signed in", "sign in to continue") });
    renderAt("/opportunities");
    fireEvent.click(await screen.findByRole("button", { name: "Sign in" }));
    expect(signinRedirect).toHaveBeenCalledOnce();
    expect(screen.queryByRole("heading", { name: "Opportunities" })).not.toBeInTheDocument();
  });

  it("shows the API's problem with a retry when /me fails", async () => {
    let calls = 0;
    fakeApi({
      "GET /me": () =>
        ++calls === 1 ? problem(503, "Unavailable", "try again shortly") : onboardedMe,
    });
    renderAt("/");
    expect(await screen.findByRole("alert")).toHaveTextContent("try again shortly");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(
      await screen.findByRole("heading", { level: 1, name: /^Good (morning|afternoon|evening)/ }),
    ).toBeInTheDocument();
  });

  it("says the API could not be reached on a network error", async () => {
    vi.stubGlobal("fetch", async () => {
      throw new TypeError("Failed to fetch");
    });
    renderAt("/");
    expect(await screen.findByRole("alert")).toHaveTextContent("Home Base could not be reached.");
  });

  it("shows the screen to an onboarded founder", async () => {
    fakeApi({ "GET /me": () => onboardedMe });
    renderAt("/applications");
    expect(await screen.findByRole("heading", { name: "Applications" })).toBeInTheDocument();
  });
});

describe("onboarding (D-64)", () => {
  function notOnboarded(onPost: (body: unknown) => unknown = () => onboardedMe) {
    let company: string | null = null;
    const posted: unknown[] = [];
    fakeApi({
      "GET /me": () => ({ ...onboardedMe, company_id: company }),
      "POST /onboarding": async (request) => {
        const body = await request.json();
        posted.push(body);
        const result = onPost(body);
        if (!(result instanceof Response)) company = onboardedMe.company_id;
        return result;
      },
    });
    return posted;
  }

  it("asks a founder with no company for its name, sends it trimmed, then shows the screen", async () => {
    const posted = notOnboarded();
    renderAt("/");
    const field = await screen.findByLabelText("Company name");
    fireEvent.change(field, { target: { value: "  Mareva Seaweed  " } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(
      await screen.findByRole("heading", { level: 1, name: /^Good (morning|afternoon|evening)/ }),
    ).toBeInTheDocument();
    expect(posted).toEqual([{ company_name: "Mareva Seaweed" }]);
  });

  it("does not send an empty or blank name", async () => {
    const posted = notOnboarded();
    renderAt("/");
    const field = await screen.findByLabelText("Company name");
    const button = screen.getByRole("button", { name: "Continue" });
    expect(button).toBeDisabled();
    fireEvent.change(field, { target: { value: "   " } });
    expect(button).toBeDisabled();
    const form = field.closest("form");
    if (!form) throw new Error("no form");
    fireEvent.submit(form);
    expect(posted).toEqual([]);
  });

  it("shows the API's reason when the company cannot be created", async () => {
    notOnboarded(() => problem(409, "Conflict", "you already have a company"));
    renderAt("/");
    fireEvent.change(await screen.findByLabelText("Company name"), { target: { value: "Mareva" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("you already have a company");
  });
});

describe("sign-in callback", () => {
  it("exchanges the code and goes to Today", async () => {
    signinRedirectCallback.mockResolvedValue({});
    fakeApi({ "GET /me": () => onboardedMe });
    const router = renderAt("/signed-in?code=abc&state=xyz");
    await waitFor(() => expect(router.state.location.pathname).toBe("/"));
    expect(signinRedirectCallback).toHaveBeenCalledOnce();
  });
});
