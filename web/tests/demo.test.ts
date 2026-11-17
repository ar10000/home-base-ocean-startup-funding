import { demoFetch, snapshotKey } from "../src/demo/install";
import snapshot from "../src/demo/snapshot.json";

const at = (path: string, method = "GET") =>
  new Request(`https://example.github.io/home-base/api${path}`, { method });

describe("public demo (D-79)", () => {
  it("keys a request by method, path and the list filters in recorded order", () => {
    expect(snapshotKey(at("/today"))).toBe("GET /today");
    expect(snapshotKey(at("/opportunities?decision=later&fit=possible"))).toBe(
      "GET /opportunities?fit=possible&decision=later",
    );
    expect(snapshotKey(at("/opportunities?fit=&decision=null"))).toBe("GET /opportunities");
  });

  it("serves every screen's first read from the snapshot", async () => {
    for (const path of ["/me", "/today", "/opportunities", "/applications", "/profile"]) {
      const response = await demoFetch(at(path));
      expect(response.status, path).toBe(200);
    }
    const me = (await (await demoFetch(at("/me"))).json()) as (typeof snapshot)["GET /me"];
    expect(me.company_id).not.toBeNull();
  });

  it("refuses every change with a problem that says why", async () => {
    for (const method of ["POST", "PUT", "DELETE"]) {
      const response = await demoFetch(at("/intent", method));
      expect(response.status).toBe(403);
      expect(await response.json()).toMatchObject({ title: "Read-only demo" });
    }
  });

  it("answers 404 for anything not recorded", async () => {
    expect((await demoFetch(at("/opportunities/unknown"))).status).toBe(404);
  });

  it("holds fictional data only: no tokens and no real addresses", () => {
    const text = JSON.stringify(snapshot);
    expect(text).not.toMatch(/access_token|Bearer /);
    expect(text).not.toMatch(/@(?!example\.)[a-z0-9-]+\.[a-z]+/i);
    const sources = text.match(/https?:\/\/[^"]+/g) ?? [];
    expect(sources.every((u) => u.startsWith("https://example.org/"))).toBe(true);
  });
});

describe("recorded AI answers in the demo", () => {
  it("serves a recorded POST, and still refuses any other change", async () => {
    const recorded = Object.keys(snapshot).filter((k) => k.startsWith("POST "));
    for (const key of recorded) {
      const [method, path] = key.split(" ") as [string, string];
      expect((await demoFetch(at(path, method))).status, key).toBe(200);
    }
    expect((await demoFetch(at("/facts", "POST"))).status).toBe(403);
  });
});
