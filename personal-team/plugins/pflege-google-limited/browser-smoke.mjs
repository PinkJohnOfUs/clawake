// Run in the browser-enabled OpenClaw container, after compiling the backend.
// Google and the authenticated Dashboard transport are simulated. No real login.
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { createRequire } from "node:module";
import { mkdtemp, readFile, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createWebOAuth, BASE } from "./dist/oauth-web.js";
import { SCOPES } from "./dist/index.js";
const { chromium } = createRequire("/app/package.json")("playwright-core");
const dir = await mkdtemp(join(tmpdir(), "pflege-browser-test-"));
const ui = await readFile(new URL("./dist/control-ui/index.js", import.meta.url), "utf8");
let web;
const server = createServer(async (req, res) => {
  if (req.url.startsWith("/simulated-google?")) {
    const auth = new URL(req.url, origin);
    const callback = new URL(auth.searchParams.get("redirect_uri"));
    callback.searchParams.set("state", auth.searchParams.get("state"));
    callback.searchParams.set("code", "fake-code");
    res.setHeader("Content-Type", "text/html");
    res.end(`<a href="${callback.toString().replaceAll("&", "&amp;")}">Approve simulated Google login</a>`);
    return;
  }
  if (req.url.startsWith(BASE)) {
    const writeHead = res.writeHead.bind(res);
    res.writeHead = (status, headers) => {
      if (headers?.Location) {
        const auth = new URL(headers.Location);
        assert.equal(auth.origin, "https://accounts.google.com");
        assert.equal(auth.searchParams.get("code_challenge_method"), "S256");
        headers.Location = origin + "/simulated-google" + auth.search;
      }
      return writeHead(status, headers);
    };
    return web.handle(req, res);
  }
  res.setHeader("Content-Type", req.url === "/ui.js" ? "text/javascript" : "text/html");
  res.end(req.url === "/ui.js" ? ui : "<!doctype html><div id='app'></div>");
});
await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
const origin = `http://127.0.0.1:${server.address().port}`;
await writeFile(join(dir, "client.json"), JSON.stringify({ web: { client_id: "test", client_secret: "test", redirect_uris: [origin + BASE + "/callback"] } }));
web = createWebOAuth({ publicOrigin: origin, credentialsPath: join(dir, "client.json"), tokenPath: join(dir, "token.json") });
const realFetch = globalThis.fetch;
globalThis.fetch = async (url, init) => {
  assert.equal(String(url), "https://oauth2.googleapis.com/token");
  assert.ok(init.body.get("code_verifier"));
  return new Response(JSON.stringify({ access_token: "fake", refresh_token: "fake", scope: SCOPES.join(" ") }));
};
let browser;
try {
  browser = await chromium.launch({ headless: true, executablePath: process.argv[2] });
  const page = await browser.newPage();
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.context().route("**/*", route => new URL(route.request().url()).origin === origin ? route.continue() : route.abort());
  await page.exposeFunction("rpc", (method, params) => method.endsWith("status") ? web.status() : web.start(params.origin));
  await page.goto(origin);
  await page.evaluate(async () => {
    const plugin = (await import("/ui.js")).default;
    const host = { request: window.rpc, ui: {
      registerPage(p) { p.mount(document.querySelector("#app"), { host }); return () => {}; },
      registerNavigation() { return () => {}; },
    } };
    plugin.activate(host);
  });
  await page.getByText("Bereit zum Verbinden.", { exact: true }).waitFor();
  const popupPromise = page.waitForEvent("popup");
  await page.getByRole("button", { name: "Google-Konto verbinden", exact: true }).click();
  const popup = await popupPromise;
  try {
    await popup.getByRole("link", { name: "Approve simulated Google login" }).click({ timeout: 10000 });
  } catch (error) {
    console.log("Dashboard:", await page.locator("body").innerText());
    console.log("Popup:", popup.isClosed() ? "closed" : await popup.locator("body").innerText());
    throw error;
  }
  await popup.getByText("Google-Konto verbunden.", { exact: false }).waitFor();
  await page.getByRole("button", { name: "Status aktualisieren" }).click();
  await page.getByText("Token gespeichert.", { exact: false }).waitFor();
  assert.deepEqual(errors, []);
  assert.equal(JSON.parse(await readFile(join(dir, "token.json"))).refresh_token, "fake");
  console.log("PASS: native UI mount, popup POST, Google redirect, browser cookie, callback and status refresh (simulated Google).");
} finally {
  globalThis.fetch = realFetch;
  await browser?.close();
  await new Promise(resolve => server.close(resolve));
  await rm(dir, { recursive: true, force: true });
}
