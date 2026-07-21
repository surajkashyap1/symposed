// Provision a FRESH database from zero: apply every drizzle migration, then the
// hand-written cross-schema SQL (auth FK, realtime, storage, RLS) that
// drizzle-kit can't generate. Use this to stand up a new staging/test project
// so it matches production. Idempotent-ish: drizzle skips already-applied
// migrations; the manual files use `if not exists` / `create or replace` where
// they can, but they're written to run once on an empty DB.
//
// Target DB is taken from MIGRATION_DATABASE_URL (same convention as
// drizzle.config.ts and apply-sql.mjs) so it never silently hits your local
// DATABASE_URL. Point it at the SESSION pooler (port 5432).
//
//   MIGRATION_DATABASE_URL="postgresql://...:5432/postgres" npm run db:bootstrap
//
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import postgres from "postgres";

const url = process.env.MIGRATION_DATABASE_URL;
if (!url) {
  console.error(
    "Refusing to run: set MIGRATION_DATABASE_URL to the target (staging) DB.\n" +
      'e.g. MIGRATION_DATABASE_URL="postgresql://...:5432/postgres" npm run db:bootstrap'
  );
  process.exit(1);
}

// Show the target host so you can confirm you're not about to bootstrap prod.
const host = (() => {
  try {
    return new URL(url).host;
  } catch {
    return "(unparseable)";
  }
})();
console.log(`→ Bootstrapping database at ${host}\n`);

// Ordered: drizzle tables first, then the manual cross-schema layers that
// depend on those tables (and on Supabase's auth/storage schemas) existing.
const MANUAL_SQL = [
  "drizzle/manual/0001_profiles_auth_fk.sql",
  "drizzle/manual/0002_realtime_messaging.sql",
  "drizzle/manual/0003_profile_assets_storage.sql",
  "drizzle/manual/0004_enable_rls.sql",
];

// 1) drizzle-kit migrate — inherits our env, so MIGRATION_DATABASE_URL wins over
// whatever .env.local sets (dotenv doesn't override existing vars).
console.log("Applying drizzle migrations…");
execFileSync("npx", ["drizzle-kit", "migrate"], { stdio: "inherit", env: process.env });

// 2) Manual SQL, in order.
const sql = postgres(url, { prepare: false });
try {
  for (const file of MANUAL_SQL) {
    process.stdout.write(`Applying ${file} … `);
    await sql.unsafe(readFileSync(file, "utf8"));
    console.log("✓");
  }
  console.log("\nDone. Fresh database is provisioned.");
} catch (e) {
  console.error("\nFAILED:", e.message);
  process.exitCode = 1;
} finally {
  await sql.end({ timeout: 5 });
}
