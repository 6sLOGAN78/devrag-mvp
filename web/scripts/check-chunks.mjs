// Post-build assertion (UI-01): the build must emit lazy route chunks beyond the entry chunk.
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const dist = fileURLToPath(new URL("../dist", import.meta.url));
const indexHtml = join(dist, "index.html");
if (!existsSync(indexHtml)) {
  console.error("dist/index.html not found: run the build first");
  process.exit(1);
}
const html = readFileSync(indexHtml, "utf8");
const entryRefs = [...html.matchAll(/<script[^>]+src="\/assets\/([^"]+\.js)"/g)].map((m) => m[1]);
if (entryRefs.length === 0) {
  console.error("index.html references no entry script");
  process.exit(1);
}
const all = readdirSync(join(dist, "assets")).filter((f) => f.endsWith(".js"));
const lazy = all.filter((f) => !entryRefs.includes(f));
console.log(`entry chunks: ${entryRefs.join(", ")}`);
console.log(`route/lazy chunks beyond entry: ${lazy.length}`);
for (const f of lazy) console.log(`  ${f}`);
if (lazy.length < 2) {
  console.error("expected at least 2 lazy route chunks beyond the entry chunk");
  process.exit(1);
}
