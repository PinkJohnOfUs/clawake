import { createCipheriv, createDecipheriv, randomBytes, randomUUID } from "node:crypto";
import {
  chmod,
  lstat,
  mkdir,
  open,
  readFile,
  rename,
  rm,
} from "node:fs/promises";
import path from "node:path";

const FORMAT = "pflege-vault";
const FORMAT_VERSION = 1;
const ALGORITHM = "aes-256-gcm";
const NONCE_BYTES = 12;
const TAG_BYTES = 16;
const MAX_VAULT_BYTES = 16 * 1024 * 1024;
const MAX_RECORDS = 10_000;

export interface PlainRecord {
  id: string;
  key: string;
  value: string;
  alias?: string;
  relation?: string;
  updatedAt: string;
}

interface EncryptedRecord {
  id: string;
  keyVersion: number;
  nonce: string;
  ciphertext: string;
  tag: string;
}

interface VaultFile {
  format: typeof FORMAT;
  version: typeof FORMAT_VERSION;
  algorithm: typeof ALGORITHM;
  records: EncryptedRecord[];
}

export interface Keyring {
  activeVersion: number;
  keys: ReadonlyMap<number, Buffer>;
}

export interface PutInput {
  key: string;
  value: string;
  alias?: string;
  relation?: string;
}

export interface ListItem {
  key: string;
  alias?: string;
  relation?: string;
  updatedAt: string;
}

export class VaultError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "VaultError";
  }
}

function aadFor(id: string, keyVersion: number): Buffer {
  return Buffer.from(`${FORMAT}:v${FORMAT_VERSION}:${id}:key-v${keyVersion}`, "utf8");
}

function encode(buffer: Buffer): string {
  return buffer.toString("base64");
}

function decodeExact(value: unknown, bytes: number, field: string): Buffer {
  if (typeof value !== "string" || !/^[A-Za-z0-9+/]+={0,2}$/.test(value)) {
    throw new VaultError(`Vault ${field} is malformed`);
  }
  const decoded = Buffer.from(value, "base64");
  if (decoded.length !== bytes || encode(decoded) !== value) {
    throw new VaultError(`Vault ${field} is malformed`);
  }
  return decoded;
}

function isPlainRecord(value: unknown): value is PlainRecord {
  if (!value || typeof value !== "object") return false;
  const row = value as Record<string, unknown>;
  return (
    typeof row.id === "string" &&
    typeof row.key === "string" &&
    typeof row.value === "string" &&
    typeof row.updatedAt === "string" &&
    (row.alias === undefined || typeof row.alias === "string") &&
    (row.relation === undefined || typeof row.relation === "string")
  );
}

function parseEncryptedRecord(value: unknown): EncryptedRecord {
  if (!value || typeof value !== "object") {
    throw new VaultError("Vault record is malformed");
  }
  const row = value as Record<string, unknown>;
  if (
    typeof row.id !== "string" ||
    row.id.length < 1 ||
    !Number.isSafeInteger(row.keyVersion) ||
    (row.keyVersion as number) < 1 ||
    typeof row.nonce !== "string" ||
    typeof row.ciphertext !== "string" ||
    typeof row.tag !== "string"
  ) {
    throw new VaultError("Vault record is malformed");
  }
  decodeExact(row.nonce, NONCE_BYTES, "nonce");
  decodeExact(row.tag, TAG_BYTES, "authentication tag");
  decodeExact(row.ciphertext, Buffer.from(row.ciphertext, "base64").length, "ciphertext");
  return row as unknown as EncryptedRecord;
}

function parseVaultFile(value: unknown): VaultFile {
  if (!value || typeof value !== "object") {
    throw new VaultError("Vault file is malformed");
  }
  const doc = value as Record<string, unknown>;
  if (doc.format !== FORMAT || doc.version !== FORMAT_VERSION || doc.algorithm !== ALGORITHM) {
    throw new VaultError("Vault format or algorithm is unsupported");
  }
  if (!Array.isArray(doc.records) || doc.records.length > MAX_RECORDS) {
    throw new VaultError("Vault record collection is malformed or too large");
  }
  const records = doc.records.map(parseEncryptedRecord);
  if (new Set(records.map((record) => record.id)).size !== records.length) {
    throw new VaultError("Vault contains duplicate record identifiers");
  }
  return { format: FORMAT, version: FORMAT_VERSION, algorithm: ALGORITHM, records };
}

function encryptRecord(record: PlainRecord, key: Buffer, keyVersion: number): EncryptedRecord {
  const nonce = randomBytes(NONCE_BYTES);
  const cipher = createCipheriv(ALGORITHM, key, nonce, { authTagLength: TAG_BYTES });
  cipher.setAAD(aadFor(record.id, keyVersion));
  const plaintext = Buffer.from(JSON.stringify(record), "utf8");
  try {
    const ciphertext = Buffer.concat([cipher.update(plaintext), cipher.final()]);
    return {
      id: record.id,
      keyVersion,
      nonce: encode(nonce),
      ciphertext: encode(ciphertext),
      tag: encode(cipher.getAuthTag()),
    };
  } finally {
    plaintext.fill(0);
  }
}

function decryptRecord(record: EncryptedRecord, keyring: Keyring): PlainRecord {
  const key = keyring.keys.get(record.keyVersion);
  if (!key) {
    throw new VaultError("Vault key version is unavailable");
  }
  const nonce = decodeExact(record.nonce, NONCE_BYTES, "nonce");
  const tag = decodeExact(record.tag, TAG_BYTES, "authentication tag");
  let plaintext: Buffer | undefined;
  try {
    const decipher = createDecipheriv(ALGORITHM, key, nonce, { authTagLength: TAG_BYTES });
    decipher.setAAD(aadFor(record.id, record.keyVersion));
    decipher.setAuthTag(tag);
    plaintext = Buffer.concat([
      decipher.update(Buffer.from(record.ciphertext, "base64")),
      decipher.final(),
    ]);
    const parsed: unknown = JSON.parse(plaintext.toString("utf8"));
    if (!isPlainRecord(parsed) || parsed.id !== record.id) {
      throw new VaultError("Vault plaintext record is malformed");
    }
    return parsed;
  } catch (error) {
    if (error instanceof VaultError) throw error;
    throw new VaultError("Vault authentication failed or key is unavailable");
  } finally {
    nonce.fill(0);
    tag.fill(0);
    plaintext?.fill(0);
  }
}

async function ensureSecureDirectory(directory: string): Promise<void> {
  await mkdir(directory, { recursive: true, mode: 0o700 });
  const info = await lstat(directory);
  if (!info.isDirectory() || info.isSymbolicLink()) {
    throw new VaultError("Vault directory must be a real directory, not a symlink");
  }
  if (typeof process.getuid === "function" && info.uid !== process.getuid()) {
    throw new VaultError("Vault directory must be owned by the Gateway process user");
  }
  await chmod(directory, 0o700);
}

async function verifySecureFile(filePath: string): Promise<false | Awaited<ReturnType<typeof lstat>>> {
  try {
    const info = await lstat(filePath);
    if (!info.isFile() || info.isSymbolicLink()) {
      throw new VaultError("Vault path must be a regular file, not a symlink");
    }
    if (typeof process.getuid === "function" && info.uid !== process.getuid()) {
      throw new VaultError("Vault file must be owned by the Gateway process user");
    }
    if (info.size > MAX_VAULT_BYTES) {
      throw new VaultError("Vault file exceeds the configured safety limit");
    }
    if ((info.mode & 0o077) !== 0) {
      await chmod(filePath, 0o600);
    }
    return info;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return false;
    throw error;
  }
}

async function fsyncDirectory(directory: string): Promise<void> {
  const handle = await open(directory, "r");
  try {
    await handle.sync();
  } finally {
    await handle.close();
  }
}

export class VaultStore {
  readonly filePath: string;
  private queue: Promise<unknown> = Promise.resolve();

  constructor(filePath: string) {
    if (!path.isAbsolute(filePath)) {
      throw new VaultError("vaultPath must be absolute");
    }
    this.filePath = path.resolve(filePath);
  }

  private serialized<T>(operation: () => Promise<T>): Promise<T> {
    const result = this.queue.then(operation, operation);
    this.queue = result.then(
      () => undefined,
      () => undefined,
    );
    return result;
  }

  private async load(keyring: Keyring): Promise<PlainRecord[]> {
    const exists = await verifySecureFile(this.filePath);
    if (!exists) return [];
    let raw: Buffer | undefined;
    try {
      raw = await readFile(this.filePath);
      const parsed = parseVaultFile(JSON.parse(raw.toString("utf8")));
      return parsed.records.map((record) => decryptRecord(record, keyring));
    } catch (error) {
      if (error instanceof VaultError) throw error;
      throw new VaultError("Vault file cannot be parsed");
    } finally {
      raw?.fill(0);
    }
  }

  private async save(records: PlainRecord[], keyring: Keyring): Promise<void> {
    const activeKey = keyring.keys.get(keyring.activeVersion);
    if (!activeKey) throw new VaultError("Active vault key version is unavailable");
    const directory = path.dirname(this.filePath);
    await ensureSecureDirectory(directory);
    await verifySecureFile(this.filePath);
    const encrypted: VaultFile = {
      format: FORMAT,
      version: FORMAT_VERSION,
      algorithm: ALGORITHM,
      records: records.map((record) => encryptRecord(record, activeKey, keyring.activeVersion)),
    };
    const bytes = Buffer.from(`${JSON.stringify(encrypted)}\n`, "utf8");
    if (bytes.length > MAX_VAULT_BYTES) {
      bytes.fill(0);
      throw new VaultError("Vault file exceeds the configured safety limit");
    }
    const temporary = path.join(directory, `.${path.basename(this.filePath)}.${randomUUID()}.tmp`);
    let handle: Awaited<ReturnType<typeof open>> | undefined;
    try {
      handle = await open(temporary, "wx", 0o600);
      await handle.writeFile(bytes);
      await handle.sync();
      await handle.close();
      handle = undefined;
      await rename(temporary, this.filePath);
      await chmod(this.filePath, 0o600);
      await fsyncDirectory(directory);
    } finally {
      bytes.fill(0);
      await handle?.close().catch(() => undefined);
      await rm(temporary, { force: true }).catch(() => undefined);
    }
  }

  get(key: string, keyring: Keyring): Promise<PlainRecord | undefined> {
    return this.serialized(async () => (await this.load(keyring)).find((record) => record.key === key));
  }

  list(keyring: Keyring): Promise<ListItem[]> {
    return this.serialized(async () =>
      (await this.load(keyring))
        .map(({ key, alias, relation, updatedAt }) => ({ key, alias, relation, updatedAt }))
        .sort((left, right) => left.key.localeCompare(right.key)),
    );
  }

  put(input: PutInput, keyring: Keyring): Promise<{ created: boolean }> {
    return this.serialized(async () => {
      const records = await this.load(keyring);
      const existing = records.find((record) => record.key === input.key);
      const updated: PlainRecord = {
        id: existing?.id ?? randomUUID(),
        key: input.key,
        value: input.value,
        ...(input.alias === undefined ? {} : { alias: input.alias }),
        ...(input.relation === undefined ? {} : { relation: input.relation }),
        updatedAt: new Date().toISOString(),
      };
      if (existing) records[records.indexOf(existing)] = updated;
      else records.push(updated);
      await this.save(records, keyring);
      return { created: !existing };
    });
  }

  delete(key: string, keyring: Keyring): Promise<{ deleted: boolean }> {
    return this.serialized(async () => {
      const records = await this.load(keyring);
      const remaining = records.filter((record) => record.key !== key);
      if (remaining.length === records.length) return { deleted: false };
      await this.save(remaining, keyring);
      return { deleted: true };
    });
  }

  rotate(keyring: Keyring): Promise<{ recordsRotated: number; activeKeyVersion: number }> {
    return this.serialized(async () => {
      const records = await this.load(keyring);
      await this.save(records, keyring);
      return { recordsRotated: records.length, activeKeyVersion: keyring.activeVersion };
    });
  }
}

export function parseAes256Key(value: string): Buffer {
  return decodeExact(value, 32, "key");
}
