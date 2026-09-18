import assert from "node:assert/strict";
import test from "node:test";
import { assertOutsideWorkspace, isAgentAllowed } from "../dist/access.js";
import { VaultError } from "../dist/vault-store.js";

test("agent ACL matches exactly and fails closed without an agent id", () => {
  assert.equal(isAgentAllowed("pflege-agent", "pflege-agent"), true);
  assert.equal(isAgentAllowed("other-agent", "pflege-agent"), false);
  assert.equal(isAgentAllowed(undefined, "pflege-agent"), false);
});

test("vault path must be outside a known workspace", () => {
  assert.doesNotThrow(() => assertOutsideWorkspace("/var/lib/openclaw/pflege-vault/vault.json", "/workspace"));
  assert.throws(() => assertOutsideWorkspace("/workspace/private/vault.json", "/workspace"), VaultError);
  assert.throws(() => assertOutsideWorkspace("/var/lib/openclaw/pflege-vault/vault.json", undefined), VaultError);
});
