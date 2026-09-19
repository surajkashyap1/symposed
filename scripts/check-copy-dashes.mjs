// House-style guard (Website Changes spec §11): no em dashes or en dashes in
// prose or generated copy. Compound hyphens (pre-populated, non-English) use
// the ordinary hyphen character and are unaffected. Ranges use the word "to".
//
// This scanner flags em/en dashes in *rendered* copy only: it strips line and
// block comments first, so the many em dashes in code comments do not trip it.
// Run with `npm run check:dashes`; exits non-zero if any are found, so it can
// back a pre-commit hook or CI step.
//
// Usage: node scripts/check-copy-dashes.mjs [dir]

import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, extname } from "node:path";

const ROOT = process.argv[2] ?? "src";
const EXTS = new Set([".ts", ".tsx", ".mjs", ".js", ".jsx"]);
const DASH = /[–—]/; // en dash, em dash

// TODO(§11): the privacy notice is a long legal document imported as one HTML
// string and still contains em/en dashes (including mangled table artifacts
// from its source conversion). It needs a careful manual pass, ideally
// regenerated from the source, before it can be un-ignored here.
const IGNORE = new Set(["src/app/privacy/page.tsx"]);

/** Blank out // line comments and /* *\/ block comments so we only scan copy. */
function stripComments(source) {
  let out = "";
  let i = 0;
  let inBlock = false;
  let inLine = false;
  // Track strings so a "//" inside a string literal is not treated as comment.
  let quote = "";
  while (i < source.length) {
    const c = source[i];
    const next = source[i + 1];
    if (inLine) {
      if (c === "\n") { inLine = false; out += c; }
      else out += " ";
      i++;
      continue;
    }
    if (inBlock) {
      if (c === "*" && next === "/") { inBlock = false; out += "  "; i += 2; }
      else { out += c === "\n" ? "\n" : " "; i++; }
      continue;
    }
    if (quote) {
      out += c;
      if (c === "\\") { out += next ?? ""; i += 2; continue; }
      if (c === quote) quote = "";
      i++;
      continue;
    }
    if (c === '"' || c === "'" || c === "`") { quote = c; out += c; i++; continue; }
    if (c === "/" && next === "/") { inLine = true; out += "  "; i += 2; continue; }
    if (c === "/" && next === "*") { inBlock = true; out += "  "; i += 2; continue; }
    out += c;
    i++;
  }
  return out;
}

function walk(dir, files = []) {
  for (const entry of readdirSync(dir)) {
    const p = join(dir, entry);
    const s = statSync(p);
    if (s.isDirectory()) {
      if (entry === "node_modules" || entry === ".next") continue;
      walk(p, files);
    } else if (EXTS.has(extname(p))) {
      files.push(p);
    }
  }
  return files;
}

let offenders = 0;
for (const file of walk(ROOT)) {
  if (IGNORE.has(file)) continue;
  const raw = readFileSync(file, "utf8");
  const scannable = stripComments(raw);
  const lines = scannable.split("\n");
  const rawLines = raw.split("\n");
  lines.forEach((line, idx) => {
    if (DASH.test(line)) {
      offenders++;
      console.log(`${file}:${idx + 1}: ${rawLines[idx].trim()}`);
    }
  });
}

if (offenders > 0) {
  console.error(`\n✖ ${offenders} em/en dash(es) found in copy. Use a comma, full stop, colon or brackets; ranges use "to" (spec §11).`);
  process.exit(1);
}
console.log("✓ No em or en dashes in copy.");
