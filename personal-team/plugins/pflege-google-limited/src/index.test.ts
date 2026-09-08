import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { getToolPluginMetadata } from "openclaw/plugin-sdk/tool-plugin";
import plugin, { SCOPES, encodeRfc2822, expandHome } from "./index.js";

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
});
