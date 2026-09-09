import { readFile, writeFile, mkdir, rename, unlink } from "node:fs/promises";
import { randomUUID } from "node:crypto";
import { homedir } from "node:os";
import { dirname, extname, resolve } from "node:path";
import { Type } from "typebox";
import { defineToolPlugin, type DefinedToolPluginEntry } from "openclaw/plugin-sdk/tool-plugin";
import { registerWebOAuth } from "./oauth-web.js";

export interface AuthConfig {
  credentialsPath: string;
  tokenPath: string;
}

interface OAuthCredentials {
  client_id: string;
  client_secret: string;
  redirect_uris: string[];
}

interface CredentialsFile {
  installed?: OAuthCredentials;
  web?: OAuthCredentials;
}

interface OAuthToken {
  access_token?: string;
  refresh_token?: string;
  expires_in?: number;
  expiry_date?: number;
  scope?: string;
  token_type?: string;
}

export const SCOPES = Object.freeze([
  "https://www.googleapis.com/auth/gmail.modify",
  "https://www.googleapis.com/auth/gmail.send",
  "https://www.googleapis.com/auth/calendar.events",
  "https://www.googleapis.com/auth/drive.readonly",
]);

const GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth";
const GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token";
const REQUEST_TIMEOUT_MS = 30_000;

export function expandHome(path: string): string {
  if (path === "~") return homedir();
  if (path.startsWith("~/")) return resolve(homedir(), path.slice(2));
  return path;
}

function authConfig(config: { credentialsPath: string; tokenPath: string }): AuthConfig {
  return { credentialsPath: config.credentialsPath, tokenPath: config.tokenPath };
}

async function readJson<T>(path: string, label: string): Promise<T> {
  let raw: string;
  try {
    raw = await readFile(expandHome(path), "utf8");
  } catch (error) {
    const code = (error as NodeJS.ErrnoException).code;
    if (code === "ENOENT") throw new Error(`${label} file not found at ${path}`);
    throw error;
  }
  try {
    return JSON.parse(raw) as T;
  } catch {
    throw new Error(`${label} file at ${path} is not valid JSON`);
  }
}

export async function readCredentials(path: string): Promise<OAuthCredentials> {
  const parsed = await readJson<CredentialsFile>(path, "OAuth credentials");
  const credentials = parsed.installed ?? parsed.web;
  if (
    !credentials?.client_id ||
    !credentials.client_secret ||
    !Array.isArray(credentials.redirect_uris) ||
    !credentials.redirect_uris[0]
  ) {
    throw new Error(
      `OAuth credentials file at ${path} must contain client_id, client_secret, and at least one redirect_uri`,
    );
  }
  return credentials;
}

async function readToken(path: string): Promise<OAuthToken> {
  return readJson<OAuthToken>(path, "OAuth token");
}

async function writeToken(path: string, token: OAuthToken): Promise<void> {
  const absolutePath = expandHome(path);
  await mkdir(dirname(absolutePath), { recursive: true, mode: 0o700 });
  const temporaryPath = `${absolutePath}.${randomUUID()}.tmp`;
  try {
    await writeFile(temporaryPath, `${JSON.stringify(token, null, 2)}\n`, {
      encoding: "utf8", mode: 0o600, flag: "wx",
    });
    await rename(temporaryPath, absolutePath);
  } finally {
    await unlink(temporaryPath).catch(() => {});
  }
}

async function fetchWithTimeout(url: string | URL, init: RequestInit = {}): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } catch (error) {
    if (controller.signal.aborted) {
      throw new Error(`Google request timed out after ${REQUEST_TIMEOUT_MS}ms`);
    }
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

async function parseGoogleResponse<T>(response: Response, operation: string): Promise<T> {
  const text = await response.text();
  let payload: unknown = undefined;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = text;
    }
  }
  if (!response.ok) {
    const detail =
      typeof payload === "object" && payload !== null
        ? JSON.stringify(payload)
        : String(payload ?? response.statusText);
    throw new Error(`${operation} failed (${response.status}): ${detail}`);
  }
  return payload as T;
}

function normalizeToken(token: OAuthToken, previous?: OAuthToken): OAuthToken {
  const now = Date.now();
  return {
    ...previous,
    ...token,
    refresh_token: token.refresh_token ?? previous?.refresh_token,
    expiry_date: token.expires_in ? now + token.expires_in * 1000 : token.expiry_date ?? previous?.expiry_date,
  };
}

function assertExactScopes(scopeText: string | undefined): void {
  if (!scopeText) throw new Error("Google returned no scope set");
  const granted = new Set(scopeText.split(/\s+/).filter(Boolean));
  const requested = new Set(SCOPES);
  const missing = SCOPES.filter((scope) => !granted.has(scope));
  const extra = [...granted].filter((scope) => !requested.has(scope));
  if (missing.length || extra.length) {
    throw new Error(
      `Google returned a scope set that does not exactly match this plugin (missing: ${missing.join(", ") || "none"}; extra: ${extra.join(", ") || "none"})`,
    );
  }
}

export async function buildAuthUrl(config: AuthConfig, flow: { redirectUri: string; state: string; challenge: string }): Promise<string> {
  const credentials = await readCredentials(config.credentialsPath);
  const url = new URL(GOOGLE_AUTH_URL);
  url.searchParams.set("client_id", credentials.client_id);
  url.searchParams.set("redirect_uri", flow.redirectUri);
  url.searchParams.set("state", flow.state);
  url.searchParams.set("code_challenge", flow.challenge);
  url.searchParams.set("code_challenge_method", "S256");
  url.searchParams.set("response_type", "code");
  url.searchParams.set("access_type", "offline");
  url.searchParams.set("prompt", "consent");
  url.searchParams.set("include_granted_scopes", "false");
  url.searchParams.set("scope", SCOPES.join(" "));
  return url.toString();
}

export async function exchangeCode(
  config: AuthConfig,
  code: string,
  flow: { redirectUri: string; verifier: string },
): Promise<{ tokenPath: string; scopes: readonly string[] }> {
  const credentials = await readCredentials(config.credentialsPath);
  const body = new URLSearchParams({
    client_id: credentials.client_id,
    client_secret: credentials.client_secret,
    code,
    grant_type: "authorization_code",
    redirect_uri: flow.redirectUri,
    code_verifier: flow.verifier,
  });
  const response = await fetchWithTimeout(GOOGLE_TOKEN_URL, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body,
  });
  const token = normalizeToken(await parseGoogleResponse<OAuthToken>(response, "OAuth code exchange"));
  if (!token.access_token || !token.refresh_token) {
    throw new Error("Google did not return both an access token and refresh token; revoke prior consent and retry");
  }
  assertExactScopes(token.scope);
  token.scope = SCOPES.join(" ");
  await writeToken(config.tokenPath, token);
  return { tokenPath: expandHome(config.tokenPath), scopes: SCOPES };
}

async function refreshAccessToken(config: AuthConfig, previous: OAuthToken): Promise<OAuthToken> {
  if (!previous.refresh_token) throw new Error("OAuth token has no refresh_token; complete OAuth again");
  const credentials = await readCredentials(config.credentialsPath);
  const response = await fetchWithTimeout(GOOGLE_TOKEN_URL, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      client_id: credentials.client_id,
      client_secret: credentials.client_secret,
      refresh_token: previous.refresh_token,
      grant_type: "refresh_token",
    }),
  });
  const token = normalizeToken(
    await parseGoogleResponse<OAuthToken>(response, "OAuth token refresh"),
    previous,
  );
  if (!token.access_token) throw new Error("Google token refresh returned no access_token");
  assertExactScopes(token.scope);
  token.scope = SCOPES.join(" ");
  await writeToken(config.tokenPath, token);
  return token;
}

async function accessToken(config: AuthConfig, forceRefresh = false): Promise<string> {
  let token = await readToken(config.tokenPath);
  const expiresSoon = !token.expiry_date || token.expiry_date <= Date.now() + 60_000;
  if (forceRefresh || !token.access_token || expiresSoon) token = await refreshAccessToken(config, token);
  if (!token.access_token) throw new Error("OAuth token has no access_token");
  return token.access_token;
}

interface GoogleRequestOptions {
  method?: "GET" | "POST" | "PATCH";
  query?: Record<string, string | number | boolean | undefined>;
  body?: unknown;
}

interface DriveFileMetadata {
  id: string;
  name: string;
  mimeType: string;
  size?: string;
  md5Checksum?: string;
  capabilities?: { canDownload?: boolean };
}

const GOOGLE_WORKSPACE_EXPORTS: Record<string, { mimeType: string; extension: string }> = {
  "application/vnd.google-apps.document": { mimeType: "application/pdf", extension: ".pdf" },
  "application/vnd.google-apps.spreadsheet": {
    mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    extension: ".xlsx",
  },
  "application/vnd.google-apps.presentation": {
    mimeType: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    extension: ".pptx",
  },
  "application/vnd.google-apps.drawing": { mimeType: "image/png", extension: ".png" },
};

export function safeDownloadName(name: string): string {
  const sanitized = name.replace(/[\\/\0]/g, "_").trim();
  if (!sanitized || sanitized === "." || sanitized === "..") {
    throw new Error("Drive download filename must contain a usable name");
  }
  return sanitized;
}

function requestedDownloadName(name: string): string {
  const safeName = safeDownloadName(name);
  if (safeName !== name.trim()) {
    throw new Error("Drive download filename must not contain directory separators or NUL bytes");
  }
  return safeName;
}

export function driveDownloadFormat(metadata: Pick<DriveFileMetadata, "name" | "mimeType">): {
  mimeType: string;
  fileName: string;
  exported: boolean;
} {
  const exportFormat = GOOGLE_WORKSPACE_EXPORTS[metadata.mimeType];
  const safeName = safeDownloadName(metadata.name);
  if (!exportFormat) return { mimeType: metadata.mimeType, fileName: safeName, exported: false };
  const fileName = extname(safeName).toLowerCase() === exportFormat.extension
    ? safeName
    : `${safeName}${exportFormat.extension}`;
  return { mimeType: exportFormat.mimeType, fileName, exported: true };
}

async function authorizedGoogleRequest(
  config: AuthConfig,
  url: URL,
  init: Omit<RequestInit, "headers"> & { headers?: Record<string, string> } = {},
): Promise<Response> {
  const request = async (forceRefresh: boolean): Promise<Response> => fetchWithTimeout(url, {
    ...init,
    headers: {
      ...init.headers,
      authorization: `Bearer ${await accessToken(config, forceRefresh)}`,
    },
  });
  let response = await request(false);
  if (response.status === 401) response = await request(true);
  return response;
}

async function googleRequest<T>(
  config: AuthConfig,
  operation: string,
  endpoint: string,
  options: GoogleRequestOptions = {},
): Promise<T> {
  const url = new URL(endpoint);
  for (const [key, value] of Object.entries(options.query ?? {})) {
    if (value !== undefined) url.searchParams.set(key, String(value));
  }
  const headers: Record<string, string> = {};
  if (options.body !== undefined) headers["content-type"] = "application/json";
  const response = await authorizedGoogleRequest(config, url, {
    method: options.method ?? "GET",
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
  return parseGoogleResponse<T>(response, operation);
}

async function readBoundedBody(response: Response, maximumBytes: number, operation: string): Promise<Buffer> {
  if (!response.ok) return parseGoogleResponse<never>(response, operation);
  const declaredLength = Number(response.headers.get("content-length"));
  if (Number.isFinite(declaredLength) && declaredLength > maximumBytes) {
    await response.body?.cancel();
    throw new Error(`${operation} exceeds the configured ${maximumBytes}-byte download limit`);
  }
  if (!response.body) return Buffer.alloc(0);
  const chunks: Uint8Array[] = [];
  let total = 0;
  const reader = response.body.getReader();
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > maximumBytes) {
        await reader.cancel();
        throw new Error(`${operation} exceeds the configured ${maximumBytes}-byte download limit`);
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  return Buffer.concat(chunks, total);
}

export interface Rfc2822Args {
  to: string;
  subject: string;
  body: string;
  cc?: string;
  bcc?: string;
  replyTo?: string;
}

function safeHeader(value: string): string {
  if (/\r|\n/.test(value)) throw new Error("Email header values must not contain line breaks");
  return value;
}

export function encodeRfc2822(args: Rfc2822Args): string {
  const headers = [
    `To: ${safeHeader(args.to)}`,
    args.cc ? `Cc: ${safeHeader(args.cc)}` : undefined,
    args.bcc ? `Bcc: ${safeHeader(args.bcc)}` : undefined,
    args.replyTo ? `Reply-To: ${safeHeader(args.replyTo)}` : undefined,
    `Subject: ${safeHeader(args.subject)}`,
    "MIME-Version: 1.0",
    'Content-Type: text/plain; charset="UTF-8"',
    "Content-Transfer-Encoding: 8bit",
  ].filter(Boolean) as string[];
  return Buffer.from(`${headers.join("\r\n")}\r\n\r\n${args.body}`, "utf8").toString("base64url");
}

function userPath(path: string): string {
  return `https://gmail.googleapis.com/gmail/v1/users/me/${path}`;
}

function calendarPath(calendarId: string, suffix: string): string {
  return `https://www.googleapis.com/calendar/v3/calendars/${encodeURIComponent(calendarId)}/${suffix}`;
}

const configSchema = Type.Object(
  {
    credentialsPath: Type.String({
      default: "~/.openclaw/secrets/pflege-google-credentials.json",
      description: "Path to a Google OAuth desktop/web client JSON file.",
    }),
    tokenPath: Type.String({
      default: "~/.openclaw/secrets/pflege-google-token.json",
      description: "Path used to read and securely persist OAuth tokens.",
    }),
    publicOrigin: Type.String({
      default: "http://127.0.0.1:18989",
      description: "Exact browser origin; HTTP only on localhost, otherwise HTTPS. No path.",
    }),
    downloadDirectory: Type.String({
      default: "~/.openclaw/downloads",
      description: "Directory where downloaded Drive files are stored.",
    }),
    maxDownloadBytes: Type.Integer({
      minimum: 1,
      maximum: 104857600,
      default: 26214400,
      description: "Maximum size of one Drive download in bytes (up to 100 MiB).",
    }),
  },
  { additionalProperties: false },
);

const APPROVAL = "This state-changing action requires concrete user approval for the specific operation and target before calling it.";

const toolPlugin = defineToolPlugin({
  id: "pflege-google-limited",
  name: "Pflege Google Limited",
  description: "Limited Google integration using native fetch and fs: Gmail read/send/manage, Calendar read/create/update, and read-only Drive access including downloads.",
  configSchema,
  tools: (tool) => [
    tool({
      name: "pflege_google_auth_start",
      label: "Start limited Google OAuth",
      description: "Explain how to connect Google in the dashboard's Google-Konto page. Never request authorization codes in chat.",
      parameters: Type.Object({}),
      async execute() {
        return {
          scopes: SCOPES,
          instructions: "Open Google-Konto in the OpenClaw dashboard in your host browser and click Google-Konto verbinden. Never send authorization codes or tokens in chat.",
        };
      },
    }),
    tool({
      name: "pflege_google_auth_complete",
      label: "Complete limited Google OAuth",
      description: `Exchange a Google authorization code and persist the resulting token locally. ${APPROVAL}`,
      parameters: Type.Object({ code: Type.String({ description: "Authorization code returned by Google." }) }),
      async execute() {
        throw new Error("Code exchange through chat is disabled. Use Google-Konto in the dashboard.");
      },
    }),
    tool({
      name: "pflege_gmail_messages_list",
      label: "List Gmail messages",
      description: "Read, list, or search current Gmail message ids and thread ids without changing messages.",
      parameters: Type.Object({
        query: Type.Optional(Type.String({ description: "Gmail search query." })),
        maxResults: Type.Optional(Type.Integer({ minimum: 1, maximum: 100, default: 10 })),
        pageToken: Type.Optional(Type.String()),
      }),
      async execute({ query, maxResults, pageToken }, config) {
        const data = await googleRequest<{ messages?: unknown[]; nextPageToken?: string; resultSizeEstimate?: number }>(
          authConfig(config),
          "Gmail messages list",
          userPath("messages"),
          { query: { q: query, maxResults: maxResults ?? 10, pageToken } },
        );
        return { count: data.messages?.length ?? 0, ...data };
      },
    }),
    tool({
      name: "pflege_gmail_message_get",
      label: "Get Gmail message",
      description: "Read, fetch, or view one current Gmail message by id without changing it.",
      parameters: Type.Object({
        id: Type.String(),
        format: Type.Optional(Type.Union([
          Type.Literal("full"),
          Type.Literal("metadata"),
          Type.Literal("minimal"),
          Type.Literal("raw"),
        ], { default: "full" })),
      }),
      async execute({ id, format }, config) {
        return googleRequest(authConfig(config), "Gmail message get", userPath(`messages/${encodeURIComponent(id)}`), {
          query: { format: format ?? "full" },
        });
      },
    }),
    tool({
      name: "pflege_gmail_message_send",
      label: "Send Gmail message",
      description: `Send one plain-text Gmail message to the specified recipients. ${APPROVAL}`,
      parameters: Type.Object({
        to: Type.String(),
        subject: Type.String(),
        body: Type.String(),
        cc: Type.Optional(Type.String()),
        bcc: Type.Optional(Type.String()),
        replyTo: Type.Optional(Type.String()),
      }),
      async execute(params, config) {
        const data = await googleRequest<{ id?: string; threadId?: string }>(
          authConfig(config),
          "Gmail message send",
          userPath("messages/send"),
          { method: "POST", body: { raw: encodeRfc2822(params) } },
        );
        return { id: data.id, threadId: data.threadId };
      },
    }),
    tool({
      name: "pflege_gmail_message_modify",
      label: "Modify Gmail labels",
      description: `Modify labels on one Gmail message, including archive, read/unread, and starred state. ${APPROVAL}`,
      parameters: Type.Object({
        id: Type.String(),
        addLabelIds: Type.Optional(Type.Array(Type.String())),
        removeLabelIds: Type.Optional(Type.Array(Type.String())),
      }),
      async execute({ id, addLabelIds, removeLabelIds }, config) {
        return googleRequest(authConfig(config), "Gmail message modify", userPath(`messages/${encodeURIComponent(id)}/modify`), {
          method: "POST",
          body: { addLabelIds: addLabelIds ?? [], removeLabelIds: removeLabelIds ?? [] },
        });
      },
    }),
    tool({
      name: "pflege_gmail_message_trash",
      label: "Move Gmail message to Trash",
      description: `Move one specific Gmail message to Trash; Google may later permanently purge it. ${APPROVAL}`,
      parameters: Type.Object({ id: Type.String() }),
      async execute({ id }, config) {
        return googleRequest(authConfig(config), "Gmail message trash", userPath(`messages/${encodeURIComponent(id)}/trash`), {
          method: "POST",
          body: {},
        });
      },
    }),
    tool({
      name: "pflege_calendar_events_list",
      label: "List Calendar events",
      description: "Read, list, or search current Google Calendar events in a time range without changing them.",
      parameters: Type.Object({
        calendarId: Type.Optional(Type.String({ default: "primary" })),
        timeMin: Type.Optional(Type.String({ description: "RFC3339 lower bound." })),
        timeMax: Type.Optional(Type.String({ description: "RFC3339 upper bound." })),
        query: Type.Optional(Type.String({ description: "Free-text Calendar search query." })),
        maxResults: Type.Optional(Type.Integer({ minimum: 1, maximum: 250, default: 25 })),
        pageToken: Type.Optional(Type.String()),
      }),
      async execute(params, config) {
        const data = await googleRequest<{ items?: unknown[]; nextPageToken?: string; nextSyncToken?: string }>(
          authConfig(config),
          "Calendar events list",
          calendarPath(params.calendarId ?? "primary", "events"),
          { query: { timeMin: params.timeMin, timeMax: params.timeMax, q: params.query, maxResults: params.maxResults ?? 25, pageToken: params.pageToken, singleEvents: true, orderBy: "startTime" } },
        );
        return { count: data.items?.length ?? 0, events: data.items ?? [], nextPageToken: data.nextPageToken, nextSyncToken: data.nextSyncToken };
      },
    }),
    tool({
      name: "pflege_calendar_event_get",
      label: "Get Calendar event",
      description: "Read, fetch, or view one current Google Calendar event by id without changing it.",
      parameters: Type.Object({ calendarId: Type.Optional(Type.String({ default: "primary" })), eventId: Type.String() }),
      async execute({ calendarId, eventId }, config) {
        return googleRequest(
          authConfig(config),
          "Calendar event get",
          calendarPath(calendarId ?? "primary", `events/${encodeURIComponent(eventId)}`),
        );
      },
    }),
    tool({
      name: "pflege_calendar_event_create",
      label: "Create Calendar event",
      description: `Create a Google Calendar event with the specified details and attendees. ${APPROVAL}`,
      parameters: Type.Object({
        calendarId: Type.Optional(Type.String({ default: "primary" })),
        summary: Type.String(),
        description: Type.Optional(Type.String()),
        location: Type.Optional(Type.String()),
        start: Type.String({ description: "RFC3339 start date-time." }),
        end: Type.String({ description: "RFC3339 end date-time." }),
        attendees: Type.Optional(Type.Array(Type.String())),
      }),
      async execute(params, config) {
        return googleRequest(
          authConfig(config),
          "Calendar event create",
          calendarPath(params.calendarId ?? "primary", "events"),
          {
            method: "POST",
            body: {
              summary: params.summary,
              description: params.description,
              location: params.location,
              start: { dateTime: params.start },
              end: { dateTime: params.end },
              attendees: params.attendees?.map((email) => ({ email })),
            },
          },
        );
      },
    }),
    tool({
      name: "pflege_calendar_event_update",
      label: "Update Calendar event",
      description: `Update selected fields on one existing Google Calendar event; this tool cannot delete events. ${APPROVAL}`,
      parameters: Type.Object({
        calendarId: Type.Optional(Type.String({ default: "primary" })),
        eventId: Type.String(),
        summary: Type.Optional(Type.String()),
        description: Type.Optional(Type.String()),
        location: Type.Optional(Type.String()),
        start: Type.Optional(Type.String({ description: "RFC3339 start date-time." })),
        end: Type.Optional(Type.String({ description: "RFC3339 end date-time." })),
        attendees: Type.Optional(Type.Array(Type.String())),
      }),
      async execute(params, config) {
        const body: Record<string, unknown> = {};
        if (params.summary !== undefined) body.summary = params.summary;
        if (params.description !== undefined) body.description = params.description;
        if (params.location !== undefined) body.location = params.location;
        if (params.start !== undefined) body.start = { dateTime: params.start };
        if (params.end !== undefined) body.end = { dateTime: params.end };
        if (params.attendees !== undefined) body.attendees = params.attendees.map((email) => ({ email }));
        if (Object.keys(body).length === 0) throw new Error("At least one event field must be supplied for update");
        return googleRequest(
          authConfig(config),
          "Calendar event update",
          calendarPath(params.calendarId ?? "primary", `events/${encodeURIComponent(params.eventId)}`),
          { method: "PATCH", body },
        );
      },
    }),
    tool({
      name: "pflege_drive_files_list",
      label: "List Drive files (read-only)",
      description: "Read, list, browse, or search Google Drive file and folder metadata without any write capability.",
      parameters: Type.Object({
        query: Type.Optional(Type.String({ description: "Google Drive files.list query." })),
        pageSize: Type.Optional(Type.Integer({ minimum: 1, maximum: 1000, default: 25 })),
        pageToken: Type.Optional(Type.String()),
      }),
      async execute({ query, pageSize, pageToken }, config) {
        const data = await googleRequest<{ files?: unknown[]; nextPageToken?: string }>(
          authConfig(config),
          "Drive files list",
          "https://www.googleapis.com/drive/v3/files",
          {
            query: {
              q: query,
              pageSize: pageSize ?? 25,
              pageToken,
              fields: "nextPageToken,files(id,name,mimeType,modifiedTime,createdTime,webViewLink,parents,size,owners(displayName,emailAddress))",
            },
          },
        );
        return { count: data.files?.length ?? 0, ...data };
      },
    }),
    tool({
      name: "pflege_drive_file_get",
      label: "Get Drive file metadata (read-only)",
      description: "Read, fetch, or view metadata for one Google Drive file without downloading or changing its contents.",
      parameters: Type.Object({ fileId: Type.String() }),
      async execute({ fileId }, config) {
        return googleRequest(
          authConfig(config),
          "Drive file metadata get",
          `https://www.googleapis.com/drive/v3/files/${encodeURIComponent(fileId)}`,
          { query: { fields: "id,name,mimeType,modifiedTime,createdTime,webViewLink,parents,size,owners(displayName,emailAddress),trashed" } },
        );
      },
    }),
    tool({
      name: "pflege_drive_file_download",
      label: "Download Drive file (read-only)",
      description: "Download one Google Drive file into the configured local download directory without changing Drive. Google Docs, Sheets, Slides, and Drawings are exported as PDF, XLSX, PPTX, and PNG respectively.",
      parameters: Type.Object({
        fileId: Type.String(),
        fileName: Type.Optional(Type.String({ description: "Optional local filename; directory components are not allowed." })),
      }),
      async execute({ fileId, fileName }, config) {
        const auth = authConfig(config);
        const metadata = await googleRequest<DriveFileMetadata>(
          auth,
          "Drive file download metadata",
          `https://www.googleapis.com/drive/v3/files/${encodeURIComponent(fileId)}`,
          { query: { fields: "id,name,mimeType,size,md5Checksum,capabilities(canDownload)" } },
        );
        if (metadata.capabilities?.canDownload === false) {
          throw new Error(`Drive file '${metadata.name}' does not permit downloading`);
        }
        const format = driveDownloadFormat(metadata);
        const maximumBytes = config.maxDownloadBytes ?? 26_214_400;
        if (metadata.size !== undefined && Number(metadata.size) > maximumBytes) {
          throw new Error(`Drive file download exceeds the configured ${maximumBytes}-byte download limit`);
        }
        const suffix = format.exported ? "/export" : "";
        const url = new URL(`https://www.googleapis.com/drive/v3/files/${encodeURIComponent(fileId)}${suffix}`);
        if (format.exported) url.searchParams.set("mimeType", format.mimeType);
        else url.searchParams.set("alt", "media");
        const response = await authorizedGoogleRequest(auth, url);
        const contents = await readBoundedBody(response, maximumBytes, "Drive file download");
        const localName = fileName === undefined ? format.fileName : requestedDownloadName(fileName);
        const downloadDirectory = expandHome(config.downloadDirectory ?? "~/.openclaw/downloads");
        await mkdir(downloadDirectory, { recursive: true, mode: 0o700 });
        const destinationPath = resolve(downloadDirectory, localName);
        await writeFile(destinationPath, contents, { flag: "wx", mode: 0o600 });
        return {
          fileId: metadata.id,
          sourceName: metadata.name,
          path: destinationPath,
          mimeType: format.mimeType,
          bytes: contents.byteLength,
          exported: format.exported,
          md5Checksum: metadata.md5Checksum,
        };
      },
    }),
  ],
});

const plugin: DefinedToolPluginEntry = toolPlugin;
const registerTools = toolPlugin.register;
plugin.register = (api) => {
  registerTools(api);
  registerWebOAuth(api);
};
export default plugin;
