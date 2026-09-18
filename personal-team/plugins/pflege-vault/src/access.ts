import path from "node:path";
import { VaultError } from "./vault-store.js";

export function isAgentAllowed(agentId: string | undefined, allowedAgentId: string): boolean {
  return typeof agentId === "string" && agentId === allowedAgentId;
}

export function assertOutsideWorkspace(
  vaultPath: string,
  workspaceDir: string | undefined,
): void {
  if (!workspaceDir) throw new VaultError("Workspace boundary is unavailable; vault access denied");
  const workspace = path.resolve(workspaceDir);
  const relative = path.relative(workspace, path.resolve(vaultPath));
  if (relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative))) {
    throw new VaultError("vaultPath must be outside the agent workspace");
  }
}
