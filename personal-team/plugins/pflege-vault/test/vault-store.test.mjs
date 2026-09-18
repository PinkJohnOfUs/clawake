import assert from "node:assert/strict";
import { randomBytes } from "node:crypto";
import { mkdtemp, readFile, stat, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { VaultError, VaultStore } from "../dist/vault-store.js";

function ephemeralKeyring(activeVersion = 1, previous = []) {
  const keys = new Map(previous);
  keys.set(activeVersion, randomBytes(32));
  return { activeVersion, keys };
}

function clearKeyring(keyring) {
  for (const key of keyring.keys.values()) key.fill(0);
}

async function fixture() {
  const root = await mkdtemp(path.join(os.tmpdir(), "pflege-vault-test-"));
  return { root, file: path.join(root, "state", "vault.json") };
}

test("round-trips records while keeping plaintext out of the file", async () => {
  const { file } = await fixture();
  const store = new VaultStore(file);
  const keyring = ephemeralKeyring();
  try {
    await store.put(
      { key: "example-key", value: "synthetic-value", alias: "example-alias", relation: "relative" },
      keyring,
    );
    const record = await store.get("example-key", keyring);
    assert.equal(record?.value, "synthetic-value");
    assert.equal(record?.alias, "example-alias");

    const ciphertext = await readFile(file, "utf8");
    assert.doesNotMatch(ciphertext, /example-key|synthetic-value|example-alias|relative/);
    assert.equal(JSON.parse(ciphertext).algorithm, "aes-256-gcm");
    assert.equal((await stat(file)).mode & 0o777, 0o600);
    assert.equal((await stat(path.dirname(file))).mode & 0o777, 0o700);
  } finally {
    clearKeyring(keyring);
  }
});

test("uses a fresh nonce whenever records are rewritten", async () => {
  const { file } = await fixture();
  const store = new VaultStore(file);
  const keyring = ephemeralKeyring();
  try {
    await store.put({ key: "alpha", value: "one" }, keyring);
    const first = JSON.parse(await readFile(file, "utf8")).records[0].nonce;
    await store.put({ key: "alpha", value: "one" }, keyring);
    const second = JSON.parse(await readFile(file, "utf8")).records[0].nonce;
    assert.notEqual(first, second);
  } finally {
    clearKeyring(keyring);
  }
});

test("detects ciphertext tampering", async () => {
  const { file } = await fixture();
  const store = new VaultStore(file);
  const keyring = ephemeralKeyring();
  try {
    await store.put({ key: "alpha", value: "one" }, keyring);
    const document = JSON.parse(await readFile(file, "utf8"));
    const bytes = Buffer.from(document.records[0].ciphertext, "base64");
    bytes[0] ^= 1;
    document.records[0].ciphertext = bytes.toString("base64");
    await writeFile(file, JSON.stringify(document), { mode: 0o600 });
    await assert.rejects(() => store.get("alpha", keyring), VaultError);
  } finally {
    clearKeyring(keyring);
  }
});

test("rotates all records to a new explicit key version", async () => {
  const { file } = await fixture();
  const store = new VaultStore(file);
  const oldKeyring = ephemeralKeyring(1);
  let rotated;
  try {
    await store.put({ key: "alpha", value: "one" }, oldKeyring);
    const oldKey = oldKeyring.keys.get(1);
    rotated = ephemeralKeyring(2, [[1, Buffer.from(oldKey)]]);
    const outcome = await store.rotate(rotated);
    assert.deepEqual(outcome, { recordsRotated: 1, activeKeyVersion: 2 });
    assert.equal(JSON.parse(await readFile(file, "utf8")).records[0].keyVersion, 2);
    assert.equal((await store.get("alpha", rotated))?.value, "one");

    const newOnly = { activeVersion: 2, keys: new Map([[2, Buffer.from(rotated.keys.get(2))]]) };
    try {
      assert.equal((await store.get("alpha", newOnly))?.value, "one");
    } finally {
      clearKeyring(newOnly);
    }
  } finally {
    clearKeyring(oldKeyring);
    if (rotated) clearKeyring(rotated);
  }
});

test("deletes a logical record without leaving it in the active file", async () => {
  const { file } = await fixture();
  const store = new VaultStore(file);
  const keyring = ephemeralKeyring();
  try {
    await store.put({ key: "alpha", value: "one" }, keyring);
    assert.deepEqual(await store.delete("alpha", keyring), { deleted: true });
    assert.equal(await store.get("alpha", keyring), undefined);
    assert.equal(JSON.parse(await readFile(file, "utf8")).records.length, 0);
  } finally {
    clearKeyring(keyring);
  }
});
