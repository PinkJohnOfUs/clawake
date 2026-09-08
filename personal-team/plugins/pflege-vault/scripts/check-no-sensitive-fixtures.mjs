import { readFile, readdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const forbiddenNames = /(^|\/)(\.env|.*\.pem|.*\.key|vault\.json)$/i;
const forbiddenText = /(BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY|Versichertennummer|Authorization:\s*Bearer)/i;

async function walk(directory) {
  const files = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    if (["node_modules", "dist", ".git"].includes(entry.name)) continue;
    const absolute = path.join(directory, entry.name);
    if (entry.isDirectory()) files.push(...(await walk(absolute)));
    else files.push(absolute);
  }
  return files;
}

for (const file of await walk(root)) {
  const relative = path.relative(root, file).split(path.sep).join("/");
  if (relative === "scripts/check-no-sensitive-fixtures.mjs") continue;
  if (forbiddenNames.test(relative)) throw new Error(`Forbidden sensitive fixture path: ${relative}`);
  const text = await readFile(file, "utf8");
  if (forbiddenText.test(text)) throw new Error(`Forbidden sensitive fixture marker: ${relative}`);
}

console.log("No sensitive fixture markers found.");
