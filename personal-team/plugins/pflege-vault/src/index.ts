import path from "node:path";
import { definePluginEntry, type OpenClawPluginApi } from "openclaw/plugin-sdk/plugin-entry";
import { assertOutsideWorkspace, isAgentAllowed } from "./access.js";
import { parseAes256Key, VaultError, VaultStore, type Keyring } from "./vault-store.js";

interface ResolvedPreviousKey {
  version: number;
  key: string;
}

interface ResolvedConfig {
  vaultPath: string;
  allowedAgentId: string;
  activeKeyVersion: number;
  masterKey: string;
  previousKeys: ResolvedPreviousKey[];
}

type ToolParams = {
  action?: unknown;
  key?: unknown;
  value?: unknown;
  alias?: unknown;
  relation?: unknown;
  confirmed?: unknown;
};

const parameters = {
  type: "object",
  additionalProperties: false,
  properties: {
    action: { type: "string", enum: ["put", "get", "list", "delete", "rotate"] },
    key: { type: "string", minLength: 1, maxLength: 200 },
    value: { type: "string", maxLength: 65536 },
    alias: { type: "string", maxLength: 500 },
    relation: { type: "string", maxLength: 500 },
    confirmed: {
      type: "boolean",
      description: "Required for persistence, deletion, and key rotation after the human has approved the specific operation.",
    },
  },
  required: ["action"],
} as const;

function parseConfig(value: unknown): ResolvedConfig {
  if (!value || typeof value !== "object") throw new VaultError("Plugin configuration is missing");
  const raw = value as Record<string, unknown>;
  if (typeof raw.vaultPath !== "string" || !path.isAbsolute(raw.vaultPath)) {
    throw new VaultError("vaultPath must be an absolute path");
  }
  if (typeof raw.allowedAgentId !== "string" || raw.allowedAgentId.trim().length === 0) {
    throw new VaultError("allowedAgentId is required");
  }
  if (!Number.isSafeInteger(raw.activeKeyVersion) || (raw.activeKeyVersion as number) < 1) {
    throw new VaultError("activeKeyVersion must be a positive integer");
  }
  if (typeof raw.masterKey !== "string") {
    throw new VaultError("masterKey SecretRef was not materialized");
  }
  const previousKeys = raw.previousKeys ?? [];
  if (!Array.isArray(previousKeys) || previousKeys.length > 8) {
    throw new VaultError("previousKeys must be an array with at most eight entries");
  }
  const parsedPrevious = previousKeys.map((item) => {
    if (!item || typeof item !== "object") throw new VaultError("previousKeys entry is invalid");
    const row = item as Record<string, unknown>;
    if (!Number.isSafeInteger(row.version) || (row.version as number) < 1 || typeof row.key !== "string") {
      throw new VaultError("previousKeys entry is invalid or unresolved");
    }
    return { version: row.version as number, key: row.key };
  });
  const versions = [raw.activeKeyVersion as number, ...parsedPrevious.map((item) => item.version)];
  if (new Set(versions).size !== versions.length) throw new VaultError("Vault key versions must be unique");
  return {
    vaultPath: path.resolve(raw.vaultPath),
    allowedAgentId: raw.allowedAgentId.trim(),
    activeKeyVersion: raw.activeKeyVersion as number,
    masterKey: raw.masterKey,
    previousKeys: parsedPrevious,
  };
}

function buildKeyring(config: ResolvedConfig): Keyring {
  const keys = new Map<number, Buffer>();
  try {
    keys.set(config.activeKeyVersion, parseAes256Key(config.masterKey));
    for (const previous of config.previousKeys) {
      keys.set(previous.version, parseAes256Key(previous.key));
    }
    return { activeVersion: config.activeKeyVersion, keys };
  } catch (error) {
    for (const key of keys.values()) key.fill(0);
    throw error;
  }
}

function clearKeyring(keyring: Keyring): void {
  for (const key of keyring.keys.values()) key.fill(0);
}

function requiredString(params: ToolParams, field: "key" | "value"): string {
  const value = params[field];
  if (typeof value !== "string" || (field === "key" && value.trim().length === 0)) {
    throw new VaultError(`${field} is required for this action`);
  }
  return field === "key" ? value.trim() : value;
}

function optionalString(params: ToolParams, field: "alias" | "relation"): string | undefined {
  const value = params[field];
  if (value === undefined) return undefined;
  if (typeof value !== "string") throw new VaultError(`${field} must be a string`);
  return value;
}

function result(details: unknown) {
  return {
    content: [{ type: "text", text: JSON.stringify(details) }],
    details,
  };
}

export default definePluginEntry({
  id: "pflege-vault",
  name: "Pflege Vault",
  description: "Purpose-bound encrypted key/value storage for the Pflegebetreuer agent.",
  register(api: OpenClawPluginApi) {
    const config = parseConfig(api.pluginConfig);
    const store = new VaultStore(config.vaultPath);
    api.registerTool(
      (context) => {
        if (!isAgentAllowed(context.agentId, config.allowedAgentId)) return null;
        assertOutsideWorkspace(config.vaultPath, context.workspaceDir);
        return {
          name: "pflege_vault",
          description:
            "Store and retrieve only purpose-approved Pflege key/value facts with optional alias/relation metadata. Never store Gmail messages, credentials, or unapproved health data. put/delete/rotate require specific human confirmation.",
          parameters,
          executionMode: "sequential",
          async execute(_toolCallId: string, rawParams: unknown) {
            const params = (rawParams ?? {}) as ToolParams;
            const action = params.action;
            if (!["put", "get", "list", "delete", "rotate"].includes(String(action))) {
              throw new VaultError("Unsupported vault action");
            }
            if (["put", "delete", "rotate"].includes(String(action)) && params.confirmed !== true) {
              throw new VaultError("Specific human confirmation is required for this action");
            }
            const keyring = buildKeyring(config);
            try {
              if (action === "put") {
                const response = await store.put(
                  {
                    key: requiredString(params, "key"),
                    value: requiredString(params, "value"),
                    alias: optionalString(params, "alias"),
                    relation: optionalString(params, "relation"),
                  },
                  keyring,
                );
                return result({ action, ...response });
              }
              if (action === "get") {
                const record = await store.get(requiredString(params, "key"), keyring);
                return result({ action, found: Boolean(record), record: record ?? null });
              }
              if (action === "list") {
                return result({ action, entries: await store.list(keyring) });
              }
              if (action === "delete") {
                return result({ action, ...(await store.delete(requiredString(params, "key"), keyring)) });
              }
              return result({ action, ...(await store.rotate(keyring)) });
            } finally {
              clearKeyring(keyring);
            }
          },
        };
      },
      { name: "pflege_vault", optional: true },
    );
  },
});
