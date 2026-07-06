<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.
<!-- END:nextjs-agent-rules -->

# Research Platform

UK-focused two-sided marketplace connecting university students and healthcare
professionals with research opportunities (projects, audits, posters). Goal:
"the easiest way to get your first publication." Full product plan lives in
`docs/` — read it before adding features.

## Stack
- **Next.js 16** (App Router) + **TypeScript** + **Tailwind CSS**, `src/` layout.
- **Supabase** (EU/London region): Auth + Postgres + Realtime + Storage.
- **Drizzle ORM** — schema in `src/db/schema.ts`, client in `src/db/index.ts`.
- **Resend** for email (later phase). Deploy on Vercel.

## Key references
- `docs/schema.sql` — canonical SQL schema (source of truth, hand-written).
- `src/db/schema.ts` — Drizzle mirror; keep in sync with the SQL file.
- `docs/ROADMAP.md` — phased build plan. We are building MVP Phases 0–7.

## Conventions
- DB access only from server code (server actions / route handlers / server
  components). Never import `src/db` into a client component.
- Business logic + auth checks live in server actions using the service role;
  RLS is enabled deny-all on every table as a backstop (no policies — see
  `drizzle/manual/0004_enable_rls.sql`). New tables must be added there.
- Application rate limit (3 / rolling 7 days) is computed in app logic, not a
  table — see `applications_applicant_time_idx`.
- Run `npm run db:generate` after editing the Drizzle schema, then
  `npm run db:migrate` to apply (use migrate, not push — push needs a TTY).
- Cross-schema FKs (e.g. profiles.id -> auth.users) can't be expressed in
  Drizzle. They live in `drizzle/manual/*.sql` and are applied with
  `node scripts/apply-sql.mjs <file>`. Re-run these on a fresh database.
