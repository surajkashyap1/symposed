// Removes everything created by scripts/seed-load.mjs. Deleting auth.users
// rows cascades to profiles (manual FK 0001) and from there to projects,
// applications, questions, reviews, notifications, saved_projects, etc.
//   node scripts/seed-load-cleanup.mjs
import postgres from "postgres";
import { config } from "dotenv";

config({ path: ".env.local" });

const sql = postgres(process.env.DATABASE_URL, { prepare: false, max: 2 });

const counts = async () => {
  const [r] = await sql`
    select
      (select count(*)::int from auth.users where email like 'loadtest.%') as users,
      (select count(*)::int from public.profiles where email like 'loadtest.%') as profiles,
      (select count(*)::int from public.projects) as projects_total,
      (select count(*)::int from public.applications) as applications_total
  `;
  return r;
};

console.log("before:", await counts());
// Batch the delete so a single giant cascade doesn't hit statement timeouts.
let total = 0;
for (;;) {
  const rows = await sql`
    delete from auth.users
    where id in (
      select id from auth.users where email like 'loadtest.%' limit 100
    )
    returning id
  `;
  total += rows.length;
  if (rows.length === 0) break;
  process.stdout.write(`\rdeleted ${total} users...`);
}
console.log(`\nafter:`, await counts());
await sql.end();
