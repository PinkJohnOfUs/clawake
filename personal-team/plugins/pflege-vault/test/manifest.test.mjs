import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const manifestUrl = new URL("../openclaw.plugin.json", import.meta.url);

test("manifest keeps the tool optional and declares SecretRef materialization", async () => {
  const manifest = JSON.parse(await readFile(manifestUrl, "utf8"));
  assert.deepEqual(manifest.contracts.tools, ["pflege_vault"]);
  assert.equal(manifest.toolMetadata.pflege_vault.optional, true);
  assert.equal(manifest.configSchema.$defs.secretRef.properties.source.const, "store");
  assert.deepEqual(
    manifest.configContracts.secretInputs.paths.map((item) => item.path),
    ["masterKey", "previousKeys.*.key"],
  );
  assert.equal(manifest.configSchema.properties.masterKey.$ref, "#/$defs/secretInput");
  assert.equal(manifest.configSchema.$defs.secretInput.anyOf[1].$ref, "#/$defs/secretRef");
});
