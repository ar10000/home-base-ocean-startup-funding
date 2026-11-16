import { randomBytes } from "node:crypto";
import { expect, test } from "@playwright/test";

// The Phase 1 workflow on the local stack with fictional data (plan, week 3): a new founder
// signs up, sets up a company, fills and approves facts on the Profile (D-74), sees the match
// become Confirmed, decides, starts the application, answers and approves a question, and
// marks it submitted.

test("golden path: sign up to a submitted application", async ({ page }) => {
  const email = `e2e-${randomBytes(4).toString("hex")}@example.test`;
  const password = randomBytes(12).toString("base64url");

  await test.step("sign up through Keycloak", async () => {
    await page.goto("/");
    await page.getByRole("button", { name: "Sign in" }).click();
    await page.waitForURL(/\/realms\/home-base\//);
    await page.getByRole("link", { name: /register/i }).click();
    await page.locator("#email").fill(email);
    await page.locator("#password").fill(password);
    await page.locator("#password-confirm").fill(password);
    await page.locator("#firstName").fill("Inês");
    await page.locator("#lastName").fill("Example");
    await page.locator("input[type=submit], button[type=submit]").first().click();
    await page.waitForURL(/localhost:5173/);
  });

  await test.step("set up the company, then Today", async () => {
    await page.getByLabel("Company name").fill("Mareva Seaweed");
    await page.getByRole("button", { name: "Continue" }).click();
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(
      /^Good (morning|afternoon|evening), Inês$/,
    );
    await expect(page.getByText("Your one thing today")).toBeVisible();
  });

  await test.step("fill and approve the profile facts the grant checks", async () => {
    await page
      .getByRole("navigation", { name: "Main" })
      .getByRole("link", { name: "Profile" })
      .click();
    for (const [name, value] of [
      ["Country", "PT"],
      ["Technology readiness level", "5"],
    ] as const) {
      const card = page.locator("li", {
        has: page.locator("span.font-semibold", { hasText: new RegExp(`^${name}$`) }),
      });
      await card.getByLabel(name, { exact: true }).selectOption(value);
      await card.getByRole("button", { name: "Save" }).click();
      await card.getByRole("button", { name: "Approve" }).click();
      await expect(card.getByText("Approved")).toBeVisible();
    }
  });

  await test.step("find a match, now Confirmed", async () => {
    await page
      .getByRole("navigation", { name: "Main" })
      .getByRole("link", { name: "Opportunities" })
      .click();
    await expect(page.getByRole("button", { name: /^All \d+$/ })).toBeVisible();
    await page.getByRole("link", { name: /Fictional Ocean Grant/ }).click();
    await expect(
      page.getByRole("heading", { level: 1, name: "Fictional Ocean Grant" }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Eligibility, checked against your facts" }),
    ).toBeVisible();
  });

  await test.step("decide, then change the decision", async () => {
    await page.getByRole("button", { name: "Later" }).click();
    await expect(page.getByRole("button", { name: "Later" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(page.getByText("Decision: Later")).toBeVisible();
  });

  await test.step("start the application", async () => {
    await page.getByRole("button", { name: "Start application" }).click();
    await page.waitForURL(/\/applications\/[0-9a-f-]+$/);
    await expect(page.getByRole("navigation", { name: "Questions" })).toBeVisible();
  });

  await test.step("answer, autosave and approve the first question", async () => {
    await page.locator("textarea").fill("Two founders: a marine biologist and an engineer.");
    await expect(page.getByText("Saved")).toBeVisible();
    await page.getByRole("button", { name: "Approve", exact: true }).click();
    await expect(page.getByRole("button", { name: "Approved", exact: true })).toBeDisabled();
    await expect(page.getByText(/^1 of \d+ ready$/)).toBeVisible();
  });

  await test.step("mark it submitted after confirming", async () => {
    await page.getByRole("button", { name: "Mark as submitted" }).click();
    await page.getByRole("button", { name: "Yes, mark as submitted" }).click();
    await expect(page.getByText("You marked this application as submitted.")).toBeVisible();
  });

  await test.step("starting the application set Pursuing (DEC-02), shown in the history", async () => {
    await page.goto("/opportunities?decision=pursuing");
    await page.getByRole("link", { name: /Fictional Ocean Grant/ }).click();
    await expect(page.getByRole("button", { name: "Pursuing" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(page.getByText("Decision: Pursuing")).toBeVisible();
  });
});
