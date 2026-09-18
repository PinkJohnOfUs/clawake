import { createHash } from "node:crypto";
import { mkdtemp, writeFile, readFile, stat, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Readable } from "node:stream";
import type { IncomingMessage, ServerResponse } from "node:http";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { BASE, createWebOAuth, registerWebOAuth, validateOrigin } from "./oauth-web.js";
import { SCOPES } from "./index.js";

const origin = "http://127.0.0.1:18989";
let dir: string;
let web: ReturnType<typeof createWebOAuth>;
let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(async () => {
  dir = await mkdtemp(join(tmpdir(), "pflege-oauth-test-"));
  await writeFile(join(dir, "client.json"), JSON.stringify({ web: {
    client_id: "test-client", client_secret: "test-secret", redirect_uris: [origin + BASE + "/callback"],
  } }));
  web = createWebOAuth({ publicOrigin: origin, credentialsPath: join(dir, "client.json"), tokenPath: join(dir, "token.json") });
  fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
    access_token: "test-access", refresh_token: "test-refresh", scope: SCOPES.join(" "), expires_in: 3600,
  }), { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(async () => { vi.unstubAllGlobals(); vi.useRealTimers(); await rm(dir, { recursive: true, force: true }); });

async function request(path: string, method = "GET", headers: Record<string, string> = {}, body = "") {
  const req = Readable.from(body ? [Buffer.from(body)] : []) as IncomingMessage;
  req.url = path; req.method = method; req.headers = headers;
  const result = { status: 0, headers: {} as Record<string, string>, body: "" };
  const res = {
    setHeader(k: string, v: string) { result.headers[k.toLowerCase()] = v; },
    writeHead(status: number, h: Record<string, string>) { result.status = status; for (const [k,v] of Object.entries(h)) this.setHeader(k,v); },
    end(text = "") { result.body = text; },
  } as unknown as ServerResponse;
  await web.handle(req, res);
  return result;
}
async function begin() {
  const { ticket } = await web.start(origin);
  const response = await request(BASE + "/begin", "POST", { origin, "content-type": "application/x-www-form-urlencoded" }, `ticket=${ticket}`);
  expect(response.status).toBe(303);
  const auth = new URL(response.headers.location);
  return { ticket, auth, cookie: response.headers["set-cookie"].split(";")[0], state: auth.searchParams.get("state")! };
}

describe("web OAuth security boundary", () => {
  it("allows HTTP only on loopback and rejects ambiguous origins", () => {
    for (const value of ["http://example.com", origin + "/", "https://x.test/path", "https://user@x.test"]) expect(() => validateOrigin(value)).toThrow();
    expect(validateOrigin("https://claw.example.com")).toBe("https://claw.example.com");
  });
  it("requires the configured UI origin and a one-use POST ticket", async () => {
    await expect(web.start("https://evil.test")).rejects.toThrow();
    expect((await request(BASE + "/begin")).status).toBe(405);
    const { ticket } = await web.start(origin);
    expect((await request(BASE + "/begin", "POST", { origin: "https://evil.test", "content-type": "application/x-www-form-urlencoded" }, `ticket=${ticket}`)).status).toBe(403);
    const started = await begin();
    expect((await request(BASE + "/begin", "POST", { origin, "content-type": "application/x-www-form-urlencoded" }, `ticket=${started.ticket}`)).status).toBe(403);
  });
  it("binds callback to the browser, uses PKCE, saves private tokens and rejects replay", async () => {
    const flow = await begin();
    const callback = BASE + `/callback?state=${flow.state}&code=test-code`;
    expect((await request(callback)).status).toBe(403);
    expect(fetchMock).not.toHaveBeenCalled();
    const response = await request(callback, "GET", { cookie: flow.cookie });
    expect(response.status).toBe(200);
    const form = fetchMock.mock.calls[0][1].body as URLSearchParams;
    expect(form.get("redirect_uri")).toBe(origin + BASE + "/callback");
    expect(createHash("sha256").update(form.get("code_verifier")!).digest("base64url")).toBe(flow.auth.searchParams.get("code_challenge"));
    expect(flow.auth.searchParams.get("code_challenge_method")).toBe("S256");
    expect((await stat(join(dir, "token.json"))).mode & 0o777).toBe(0o600);
    expect(response.body).not.toContain("test-access");
    expect(response.headers["cache-control"]).toBe("no-store");
    expect((await request(callback, "GET", { cookie: flow.cookie })).status).toBe(403);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
  it("expires pending flows", async () => {
    const flow = await begin();
    vi.useFakeTimers(); vi.setSystemTime(Date.now() + 11 * 60_000);
    expect((await request(BASE + `/callback?state=${flow.state}&code=x`, "GET", { cookie: flow.cookie })).status).toBe(403);
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it("rejects callbacks after a restart and missing granted scopes", async () => {
    const flow = await begin();
    const previous = web;
    web = createWebOAuth({ publicOrigin: origin, credentialsPath: join(dir, "client.json"), tokenPath: join(dir, "token.json") });
    const callback = BASE + `/callback?state=${flow.state}&code=x`;
    expect((await request(callback, "GET", { cookie: flow.cookie })).status).toBe(403);
    web = previous;
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ access_token: "x", refresh_token: "y" })));
    expect((await request(callback, "GET", { cookie: flow.cookie })).status).toBe(400);
    await expect(readFile(join(dir, "token.json"))).rejects.toThrow();
  });
  it("preserves existing tokens after denial or unexpected scopes", async () => {
    await writeFile(join(dir, "token.json"), "existing-token");
    let flow = await begin();
    expect((await request(BASE + `/callback?state=${flow.state}&error=access_denied`, "GET", { cookie: flow.cookie })).status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
    flow = await begin();
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ access_token: "x", refresh_token: "y", scope: "unexpected" })));
    expect((await request(BASE + `/callback?state=${flow.state}&code=x`, "GET", { cookie: flow.cookie })).status).toBe(400);
    expect(await readFile(join(dir, "token.json"), "utf8")).toBe("existing-token");
  });
  it("requires admin RPC and only registers the two narrowly authenticated routes", () => {
    const methods: unknown[][] = [], routes: any[] = [];
    registerWebOAuth({ pluginConfig: {}, registerGatewayMethod: (...args: unknown[]) => methods.push(args), registerHttpRoute: (route: unknown) => routes.push(route) } as any);
    expect(methods.map(m => m[2])).toEqual([{ scope: "operator.admin" }, { scope: "operator.admin" }]);
    expect(routes.map(r => [r.path, r.match, r.auth])).toEqual([[BASE + "/begin", "exact", "plugin"], [BASE + "/callback", "exact", "plugin"]]);
  });
});
