import { readFileSync } from "node:fs";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { getToolPluginMetadata } from "openclaw/plugin-sdk/tool-plugin";
import plugin, { SCOPES, driveDownloadFormat, encodeRfc2822, expandHome, safeDownloadName } from "./index.js";

const expectedTools = [
  "pflege_google_auth_start",
  "pflege_google_auth_complete",
  "pflege_gmail_messages_list",
  "pflege_gmail_message_get",
  "pflege_gmail_message_send",
  "pflege_gmail_message_modify",
  "pflege_gmail_message_trash",
  "pflege_calendar_events_list",
  "pflege_calendar_event_get",
  "pflege_calendar_event_create",
  "pflege_calendar_event_update",
  "pflege_drive_files_list",
  "pflege_drive_file_get",
  "pflege_drive_file_download",
];

const stateChangingTools = [
  "pflege_google_auth_complete",
  "pflege_gmail_message_send",
  "pflege_gmail_message_modify",
  "pflege_gmail_message_trash",
  "pflege_calendar_event_create",
  "pflege_calendar_event_update",
];

describe("limited plugin metadata", () => {
  const metadata = getToolPluginMetadata(plugin)!;
  const tools = Object.fromEntries(metadata.tools.map((tool) => [tool.name, tool]));

  it("exposes exactly the approved tool surface", () => {
    expect(metadata.id).toBe("pflege-google-limited");
    expect(metadata.tools.map((tool) => tool.name).sort()).toEqual([...expectedTools].sort());
  });

  it("requires concrete user approval in every state-changing description", () => {
    for (const name of stateChangingTools) {
      expect(tools[name].description.toLowerCase(), name).toContain("requires concrete user approval");
    }
  });

  it("does not expose Calendar delete or Drive write capabilities", () => {
    const names = metadata.tools.map((tool) => tool.name).join(" ");
    expect(names).not.toMatch(/calendar.*delete|drive.*(?:create|update|delete|trash|permission)/i);
  });
});

describe("OAuth scope boundary", () => {
  it("contains exactly the four requested scopes", () => {
    expect([...SCOPES]).toEqual([
      "https://www.googleapis.com/auth/gmail.modify",
      "https://www.googleapis.com/auth/gmail.send",
      "https://www.googleapis.com/auth/calendar.events",
      "https://www.googleapis.com/auth/drive.readonly",
    ]);
  });
});

describe("self-contained runtime entry", () => {
  it("has no googleapis or require.resolve", () => {
    const source = readFileSync(new URL("./index.ts", import.meta.url), "utf8");
    expect(source).not.toMatch(/from\s+["']googleapis["']/);
    expect(source).not.toMatch(/require\.resolve\s*\(/);
  });
});

describe("pure helpers", () => {
  it("expands only a leading home marker", () => {
    expect(expandHome("~/google/token.json")).not.toContain("~");
    expect(expandHome("/tmp/~/token.json")).toBe("/tmp/~/token.json");
  });

  it("encodes an RFC 2822 message as base64url", () => {
    const raw = encodeRfc2822({ to: "a@example.test", subject: "Hello", body: "Body" });
    expect(raw).not.toMatch(/[+/=]/);
    expect(Buffer.from(raw, "base64url").toString("utf8")).toContain("Subject: Hello\r\n");
  });

  it("rejects email header injection", () => {
    expect(() => encodeRfc2822({ to: "a@example.test\r\nBcc: x@example.test", subject: "x", body: "x" })).toThrow(/line breaks/);
  });

  it("sanitizes Drive names supplied by Google", () => {
    expect(safeDownloadName("quarter/report.pdf")).toBe("quarter_report.pdf");
    expect(() => safeDownloadName("..")).toThrow(/usable name/);
  });

  it("uses direct downloads for regular Drive files", () => {
    expect(driveDownloadFormat({ name: "photo.jpg", mimeType: "image/jpeg" })).toEqual({
      fileName: "photo.jpg",
      mimeType: "image/jpeg",
      exported: false,
    });
  });

  it("exports Google Workspace files to useful local formats", () => {
    expect(driveDownloadFormat({
      name: "Pflegeplan",
      mimeType: "application/vnd.google-apps.document",
    })).toEqual({ fileName: "Pflegeplan.pdf", mimeType: "application/pdf", exported: true });
    expect(driveDownloadFormat({
      name: "Termine",
      mimeType: "application/vnd.google-apps.spreadsheet",
    }).fileName).toBe("Termine.xlsx");
  });
});

describe("Drive download tool", () => {
  const directories: string[] = [];

  afterEach(async () => {
    vi.restoreAllMocks();
    await Promise.all(directories.splice(0).map((path) => rm(path, { recursive: true, force: true })));
  });

  it("downloads bytes into the configured directory without changing Drive", async () => {
    const directory = await mkdtemp(join(tmpdir(), "pflege-drive-download-"));
    directories.push(directory);
    const tokenPath = join(directory, "token.json");
    await writeFile(tokenPath, JSON.stringify({ access_token: "test-token", expiry_date: Date.now() + 3_600_000 }));
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({
        id: "drive-id",
        name: "bericht.txt",
        mimeType: "text/plain",
        size: "5",
        capabilities: { canDownload: true },
      }), { headers: { "content-type": "application/json" } }))
      .mockResolvedValueOnce(new Response("Hallo", { headers: { "content-length": "5" } }));
    const registered: any[] = [];
    plugin.register({
      pluginConfig: {
        credentialsPath: join(directory, "unused-credentials.json"),
        tokenPath,
        publicOrigin: "http://127.0.0.1:18989",
        downloadDirectory: directory,
        maxDownloadBytes: 100,
      },
      registerTool: (tool: unknown) => registered.push(tool),
      registerGatewayMethod: () => {},
      registerHttpRoute: () => {},
    } as any);
    const download = registered.find((tool) => tool.name === "pflege_drive_file_download");
    const result = await download.execute("call-id", { fileId: "drive-id" });

    expect(await readFile(join(directory, "bericht.txt"), "utf8")).toBe("Hallo");
    expect(JSON.parse(result.content[0].text)).toMatchObject({
      fileId: "drive-id",
      path: join(directory, "bericht.txt"),
      bytes: 5,
      exported: false,
    });
    expect(fetchMock.mock.calls[1][0].toString()).toContain("/drive/v3/files/drive-id?alt=media");
    expect(fetchMock.mock.calls.every(([, init]) => init?.method !== "POST" && init?.method !== "PATCH")).toBe(true);
  });
});
