import { createHash, randomBytes } from "node:crypto";
import { readFile } from "node:fs/promises";
import type { IncomingMessage, ServerResponse } from "node:http";
import type { OpenClawPluginApi } from "openclaw/plugin-sdk/plugin-entry";
import { buildAuthUrl, exchangeCode, expandHome, readCredentials, type AuthConfig } from "./index.js";

export const BASE = "/integrations/google";
const TTL = 10 * 60_000;
const random = () => randomBytes(32).toString("base64url");
const hash = (value: string) => createHash("sha256").update(value).digest("base64url");
type Config = AuthConfig & { publicOrigin: string };
type Pending = { expires: number; state: string; verifier: string; cookie: string; authUrl: string };

export function validateOrigin(value: string): string {
  const url = new URL(value);
  if (url.origin !== value || url.username || url.password ||
      !(url.protocol === "https:" || (url.protocol === "http:" &&
        ["127.0.0.1", "localhost", "[::1]"].includes(url.hostname)))) {
    throw new Error("publicOrigin must be an exact HTTPS origin or a loopback HTTP origin without a path.");
  }
  return url.origin;
}

/** In-memory transactions intentionally expire on restart; no OAuth codes are logged. */
export function createWebOAuth(config: Config) {
  const origin = validateOrigin(config.publicOrigin);
  const redirectUri = origin + BASE + "/callback";
  const tickets = new Map<string, Pending>();
  const states = new Map<string, Pending>();
  const secure = origin.startsWith("https:") ? "; Secure" : "";
  const cookieName = "pflege_google_oauth";
  const cookieHeader = (value: string, age: number) =>
    `${cookieName}=${value}; Path=${BASE}; HttpOnly; SameSite=Lax; Max-Age=${age}${secure}`;
  const prune = () => {
    for (const map of [tickets, states]) for (const [key, value] of map) {
      if (value.expires <= Date.now()) map.delete(key);
    }
  };
  async function ready() {
    const credentials = await readCredentials(config.credentialsPath);
    if (!credentials.redirect_uris.includes(redirectUri)) {
      throw new Error("Register the callback URI and update the OAuth client JSON file.");
    }
  }
  function reply(res: ServerResponse, code: number, text: string) {
    res.writeHead(code, { "content-type": "text/plain; charset=utf-8" });
    res.end(text);
  }
  return {
    async status() {
      let configured = false;
      try { await ready(); configured = true; } catch { /* No credential details sent to UI. */ }
      let tokenStored = false;
      try {
        const token = JSON.parse(await readFile(expandHome(config.tokenPath), "utf8"));
        tokenStored = Boolean(token.refresh_token);
      } catch { /* A stored token is not proof of current Google authorization. */ }
      return { configured, tokenStored, origin, redirectUri };
    },
    async start(browserOrigin: unknown) {
      if (browserOrigin !== origin) throw new Error("Open the dashboard at the configured publicOrigin.");
      prune();
      if (tickets.size + states.size >= 32) throw new Error("Too many pending logins; retry in ten minutes.");
      await ready();
      const verifier = random();
      const state = random();
      const ticket = random();
      const pending = { expires: Date.now() + TTL, verifier, state, cookie: random(),
        authUrl: await buildAuthUrl(config, { redirectUri, state, challenge: hash(verifier) }) };
      tickets.set(hash(ticket), pending);
      return { ticket, launchUrl: origin + BASE + "/begin" };
    },
    async handle(req: IncomingMessage, res: ServerResponse) {
      res.setHeader("Cache-Control", "no-store");
      res.setHeader("Referrer-Policy", "no-referrer");
      res.setHeader("X-Content-Type-Options", "nosniff");
      res.setHeader("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'");
      prune();
      const url = new URL(req.url ?? "/", origin);
      if (url.pathname === BASE + "/begin") {
        if (req.method !== "POST") return reply(res, 405, "POST required.");
        if (req.headers.origin !== origin ||
            req.headers["content-type"]?.split(";")[0] !== "application/x-www-form-urlencoded") {
          return reply(res, 403, "Invalid origin or content type.");
        }
        let body = "";
        for await (const chunk of req) {
          body += chunk.toString();
          if (Buffer.byteLength(body) > 1024) return reply(res, 413, "Request too large.");
        }
        const ticket = new URLSearchParams(body).get("ticket") ?? "";
        const pending = tickets.get(hash(ticket));
        if (!pending || pending.expires <= Date.now()) return reply(res, 403, "Login expired. Start again from the dashboard.");
        tickets.delete(hash(ticket));
        states.set(pending.state, pending);
        res.setHeader("Set-Cookie", cookieHeader(pending.cookie, TTL / 1000));
        res.writeHead(303, { Location: pending.authUrl });
        res.end();
        return;
      }
      if (url.pathname !== BASE + "/callback") return reply(res, 404, "Not found.");
      if (req.method !== "GET") return reply(res, 405, "GET required.");
      const state = url.searchParams.get("state") ?? "";
      const pending = states.get(state);
      const cookies = (req.headers.cookie ?? "").split(";").map(part => part.trim());
      if (!pending || !cookies.includes(`${cookieName}=${pending.cookie}`) ||
          url.searchParams.getAll("state").length !== 1) {
        return reply(res, 403, "Invalid or expired login. Start again from the dashboard in the same browser.");
      }
      states.delete(state); // Consume before any network request, including failures and denial.
      res.setHeader("Set-Cookie", cookieHeader("", 0));
      if (url.searchParams.has("error")) return reply(res, 400, "Google-Freigabe abgebrochen. Vorhandene Verbindung bleibt erhalten.");
      const code = url.searchParams.get("code");
      if (!code || code.length > 4096 || url.searchParams.getAll("code").length !== 1) return reply(res, 400, "Invalid callback.");
      try {
        await exchangeCode(config, code, { redirectUri, verifier: pending.verifier });
        reply(res, 200, "Google-Konto verbunden. Diesen Tab schließen und im Dashboard den Status aktualisieren.");
      } catch {
        reply(res, 400, "Google-Verbindung fehlgeschlagen. Client-Konfiguration und Berechtigungen prüfen und im Dashboard erneut starten.");
      }
    },
  };
}

export function registerWebOAuth(api: OpenClawPluginApi) {
  const c = api.pluginConfig ?? {};
  const web = createWebOAuth({
    credentialsPath: String(c.credentialsPath ?? "~/.openclaw/secrets/pflege-google-credentials.json"),
    tokenPath: String(c.tokenPath ?? "~/.openclaw/secrets/pflege-google-token.json"),
    publicOrigin: String(c.publicOrigin ?? "http://127.0.0.1:18989"),
  });
  for (const operation of ["status", "start"] as const) {
    api.registerGatewayMethod(`pflege-google.${operation}`, async ({ params, respond }) => {
      try {
        const result = operation === "status" ? await web.status() : await web.start(params.origin);
        respond(true, result);
      } catch {
        respond(false, undefined, { code: "INVALID_REQUEST", message: "Google-Einrichtung prüfen: Dashboard-Origin, Clientdatei und Rückrufadresse müssen passen. Offene Anmeldungen laufen nach zehn Minuten ab." });
      }
    }, { scope: "operator.admin" });
  }
  for (const path of [BASE + "/begin", BASE + "/callback"]) {
    api.registerHttpRoute({ path, match: "exact", auth: "plugin", handler: web.handle });
  }
}
