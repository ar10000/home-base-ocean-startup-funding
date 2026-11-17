// Records the public demo's snapshot (D-79): plays a fictional founder through the local
// stack (`make dev-up demo-seed dev-api dev-web`), then saves every read the web app makes
// to src/demo/snapshot.json. Run with `make demo-record`. Local only: it signs up a
// throwaway user in the local Keycloak.
import { randomBytes } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { chromium } from "@playwright/test";

const web = new URL("..", import.meta.url).pathname;
const base = "http://localhost:5173";
const email = `demo-${randomBytes(4).toString("hex")}@example.test`;
const password = randomBytes(12).toString("base64url");
const spec = JSON.parse(readFileSync(`${web}openapi.json`, "utf8"));

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 860 } });
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
page.on("console", (m) => m.type() === "error" && errors.push(m.text()));

await page.goto(base);
await page.getByRole("button", { name: "Sign in" }).click();
await page.waitForURL(/localhost:8080/);
await page.getByRole("link", { name: /register/i }).click();
await page.locator("#email").fill(email);
await page.locator("#password").fill(password);
await page.locator("#password-confirm").fill(password);
await page.locator("#firstName").fill("Inês");
await page.locator("#lastName").fill("Example");
await page.locator("input[type=submit], button[type=submit]").first().click();
await page.waitForURL(/localhost:5173/);
await page.getByLabel("Company name").fill("Mareva Seaweed");
await page.getByRole("button", { name: "Continue" }).click();
await page.getByLabel("Company name").waitFor({ state: "detached" });
await page.getByText("Your one thing today").waitFor();

// Profile: facts, one founder fact, goals, stage.
await page.goto(`${base}/profile`);
await page.getByRole("heading", { name: "Company facts" }).waitFor();
async function setFact(name, value, approve = true) {
  const card = page.locator("li", {
    has: page.locator("span.font-semibold", { hasText: new RegExp(`^${name}$`) }),
  });
  await card.getByLabel(new RegExp(`^(New )?${name}$`, "i")).selectOption(value);
  await card.getByRole("button", { name: "Save" }).click();
  if (approve) {
    await card.getByRole("button", { name: "Approve" }).click();
    await card.getByText("Approved").waitFor();
  } else {
    await card.getByRole("button", { name: "Approve" }).waitFor();
  }
}
await setFact("Country", "PT");
await setFact("Sector", "marine_living_resources");
await setFact("Legal form", "private_limited");
await setFact("Technology readiness level", "5");
await setFact("Team size", "4");
await setFact("Consortium need", "alone");
// The knowledge base (D-80): what drafts retrieve from (D-81).
async function knowledge(title, text) {
  const card = page.locator("li", {
    has: page.locator("label", { hasText: new RegExp(`^${title}$`) }),
  });
  await card.getByRole("textbox").fill(text);
  await card.getByRole("button", { name: "Save" }).click();
  await card.getByRole("button", { name: "Approve" }).click();
  await card.getByText("Approved").waitFor();
}
await knowledge(
  "What the company does",
  "Mareva Seaweed grows kelp on longlines off Peniche and turns it into a feed ingredient for fish farms.",
);
await knowledge(
  "Impact",
  "On our 2-hectare pilot line, the kelp took up an estimated 1.4 t of nitrogen in 2026, measured with the University of Example.",
);
await knowledge(
  "Team",
  "Inês (CEO) is a marine biologist with 8 years in aquaculture; Tomás (CTO) is a naval engineer who designed the longline system.",
);
await knowledge(
  "Traction",
  "One pilot with a fish farm in Nazaré since March 2026, and a letter of intent from a feed producer for 20 t a year.",
);
await page.getByLabel("Investment").check();
await page.getByRole("button", { name: "Save goals" }).click();
await page.getByText("Saved").first().waitFor();
await page.getByLabel("Your stage").selectOption("pilot");
await page.locator("#stage").getByRole("button", { name: "Save" }).click();
await page.getByText(/Stage 5 of 9/).waitFor();

// Decisions and one application in progress.
async function open(name, query = "") {
  await page.goto(`${base}/opportunities${query}`);
  await page.waitForLoadState("networkidle");
  await page.getByRole("link", { name: new RegExp(name) }).click();
  await page.getByRole("heading", { name: new RegExp(name) }).waitFor();
}
async function decide(name, label) {
  await open(name);
  await page.getByRole("button", { name: label, exact: true }).click();
  await page.getByRole("button", { name: label, exact: true, pressed: true }).waitFor();
}
await open("Green Port Innovation Voucher", "?fit=not_eligible");
await page.getByRole("button", { name: "Not for us", exact: true }).click();
await page.getByRole("button", { name: "Not for us", exact: true, pressed: true }).waitFor();
await decide("Blue Founders Accelerator", "Later");
await open("Tidal Pilot Fund");
await page.getByRole("button", { name: "Start application" }).click();
await page.waitForURL(/\/applications\//);
await page.getByRole("navigation", { name: "Questions" }).waitFor();
await page.getByRole("button", { name: "Draft with AI" }).click();
await page.getByRole("button", { name: "Redraft with AI" }).waitFor({ timeout: 60000 });
await page.getByRole("button", { name: "Approve", exact: true }).click();
await page.getByRole("button", { name: "Approved", exact: true }).waitFor();
await open("Atlantic Seaweed Innovation Grant");
await page.getByRole("button", { name: "Pursuing", exact: true }).click();
await page.getByRole("button", { name: "Pursuing", exact: true, pressed: true }).waitFor();

// Record: every GET the app makes, read with the founder's own token.
const token = await page.evaluate(() => {
  const key = Object.keys(sessionStorage).find((k) => k.startsWith("oidc.user:"));
  return JSON.parse(sessionStorage.getItem(key)).access_token;
});
async function get(path) {
  const res = await page.request.get(`${base}/api${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok()) throw new Error(`${path}: ${res.status()}`);
  return res.json();
}
const snapshot = {};
for (const path of ["/me", "/today", "/profile", "/fact-options", "/stages", "/applications"]) {
  snapshot[`GET ${path}`] = await get(path);
}
const params = spec.paths["/opportunities"].get.parameters;
const values = (n) => {
  const s = params.find((p) => p.name === n).schema;
  const ref = (s.anyOf ?? [s]).find((x) => x.$ref)?.$ref ?? s.$ref;
  return [null, ...spec.components.schemas[ref.split("/").pop()].enum];
};
for (const fit of values("fit")) {
  for (const decision of values("decision")) {
    const q = new URLSearchParams();
    if (fit) q.set("fit", fit);
    if (decision) q.set("decision", decision);
    const path = `/opportunities${q.size ? `?${q}` : ""}`;
    snapshot[`GET ${path}`] = await get(path);
  }
}
const ids = new Set(
  Object.entries(snapshot)
    .filter(([k]) => k.startsWith("GET /opportunities"))
    .flatMap(([, v]) => v.items.map((i) => i.id)),
);
for (const id of ids) {
  const item = { id };
  snapshot[`GET /opportunities/${item.id}`] = await get(`/opportunities/${item.id}`);
}
for (const item of snapshot["GET /applications"]) {
  snapshot[`GET /applications/${item.id}`] = await get(`/applications/${item.id}`);
}
// The AI's answers, recorded so a visitor can ask for them in the demo (D-79): why each
// call fits, and a draft for every question not yet approved. Recorded after the reads
// above, so the demo shows those questions empty until "Draft with AI" is clicked.
async function post(path) {
  const res = await page.request.post(`${base}/api${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok()) throw new Error(`${path}: ${res.status()}`);
  return res.json();
}
for (const id of ids) {
  if (snapshot[`GET /opportunities/${id}`].requirements.length > 0) {
    snapshot[`POST /opportunities/${id}/why-it-fits`] = await post(
      `/opportunities/${id}/why-it-fits`,
    );
  }
}
for (const item of snapshot["GET /applications"]) {
  for (const q of snapshot[`GET /applications/${item.id}`].questions) {
    if (q.state === "approved") continue;
    const path = `/applications/${item.id}/answers/${q.id}/draft`;
    snapshot[`POST ${path}`] = await post(path);
  }
}
snapshot.recorded_on = new Date().toISOString().slice(0, 10);
writeFileSync(`${web}src/demo/snapshot.json`, `${JSON.stringify(snapshot, null, 2)}\n`);
console.log(`recorded ${Object.keys(snapshot).length - 1} responses`);
console.log(errors.length ? `console errors:\n${errors.join("\n")}` : "no console errors");
await browser.close();
